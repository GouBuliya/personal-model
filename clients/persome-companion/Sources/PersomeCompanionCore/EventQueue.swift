import Foundation
#if canImport(Darwin)
import Darwin
#elseif canImport(Glibc)
import Glibc
#endif

public enum EventQueueError: Error, Equatable {
    case lockFailed(Int32)
}

public actor EventQueue {
    private let fileURL: URL
    private let lockURL: URL

    public init(fileURL: URL) throws {
        self.fileURL = fileURL
        lockURL = fileURL.appendingPathExtension("lock")
    }

    public func enqueue(_ event: MobileEvent) throws {
        try withFileLock {
            var events = try load()
            guard !events.contains(where: { $0.eventID == event.eventID }) else { return }
            events.append(event)
            try persist(events)
        }
    }

    public func pending() throws -> [MobileEvent] {
        try withFileLock { try load() }
    }

    public func count() throws -> Int {
        try withFileLock { try load().count }
    }

    public func acknowledge(eventID: String) throws {
        try withFileLock {
            var events = try load()
            events.removeAll { $0.eventID == eventID }
            try persist(events)
        }
    }

    private func load() throws -> [MobileEvent] {
        guard FileManager.default.fileExists(atPath: fileURL.path) else { return [] }
        let data = try Data(contentsOf: fileURL)
        return try JSONDecoder.persome().decode([MobileEvent].self, from: data)
    }

    private func persist(_ events: [MobileEvent]) throws {
        let data = try JSONEncoder.persome().encode(events)
        try data.write(to: fileURL, options: [.atomic, .completeFileProtection])
        try? FileManager.default.setAttributes(
            [.posixPermissions: 0o600],
            ofItemAtPath: fileURL.path
        )
    }

    private func withFileLock<T>(_ operation: () throws -> T) throws -> T {
        let directory = fileURL.deletingLastPathComponent()
        try FileManager.default.createDirectory(
            at: directory,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700]
        )
        let descriptor = systemOpenLock(lockURL.path)
        guard descriptor >= 0 else { throw EventQueueError.lockFailed(systemErrno()) }
        defer { systemClose(descriptor) }
        guard systemFlock(descriptor, LOCK_EX) == 0 else {
            throw EventQueueError.lockFailed(systemErrno())
        }
        defer { _ = systemFlock(descriptor, LOCK_UN) }
        return try operation()
    }
}

private func systemOpenLock(_ path: String) -> Int32 {
    #if canImport(Darwin)
    Darwin.open(path, O_CREAT | O_RDWR | O_CLOEXEC, S_IRUSR | S_IWUSR)
    #elseif canImport(Glibc)
    Glibc.open(path, O_CREAT | O_RDWR | O_CLOEXEC, S_IRUSR | S_IWUSR)
    #else
    -1
    #endif
}

@_silgen_name("flock")
private func systemFlock(_ descriptor: Int32, _ operation: Int32) -> Int32

private func systemClose(_ descriptor: Int32) {
    #if canImport(Darwin)
    _ = Darwin.close(descriptor)
    #elseif canImport(Glibc)
    _ = Glibc.close(descriptor)
    #endif
}

private func systemErrno() -> Int32 {
    #if canImport(Darwin)
    Darwin.errno
    #elseif canImport(Glibc)
    Glibc.errno
    #else
    -1
    #endif
}
