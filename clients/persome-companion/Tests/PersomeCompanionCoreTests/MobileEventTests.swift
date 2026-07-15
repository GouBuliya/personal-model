import Foundation
import Testing
@testable import PersomeCompanionCore

@Test func eventEncodesRuntimeContract() throws {
    let event = try MobileEvent(
        eventID: "share-001",
        capturedAt: Date(timeIntervalSince1970: 1_752_525_800),
        device: MobileDevice(id: "iphone-1", platform: .ios, name: "iPhone"),
        kind: .share,
        sourceApp: "Safari",
        title: "Personal models",
        text: "Local-first context",
        url: URL(string: "https://example.test/model")
    )

    let object = try #require(
        JSONSerialization.jsonObject(with: JSONEncoder.persome().encode(event)) as? [String: Any]
    )
    #expect(object["schema_version"] as? Int == 1)
    #expect(object["event_id"] as? String == "share-001")
    #expect(object["source_app"] as? String == "Safari")
    #expect(object["captured_at"] is String)
}

@Test func emptyEventIsRejected() {
    #expect(throws: MobileEventError.emptyContent) {
        try MobileEvent(
            device: MobileDevice(id: "iphone-1", platform: .ios),
            kind: .text
        )
    }
}

@Test func queueIsDurableAndIdempotent() async throws {
    let root = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString)
    let file = root.appending(path: "queue.json")
    let event = try MobileEvent(
        eventID: "same-event",
        capturedAt: Date(timeIntervalSince1970: 1_752_525_800),
        device: MobileDevice(id: "iphone-1", platform: .ios),
        kind: .text,
        text: "Remember this"
    )

    let queue = try EventQueue(fileURL: file)
    try await queue.enqueue(event)
    try await queue.enqueue(event)
    #expect(try await queue.pending().count == 1)

    let restored = try EventQueue(fileURL: file)
    #expect(try await restored.pending() == [event])
    try await restored.acknowledge(eventID: event.eventID)
    #expect(try await restored.pending().isEmpty)
}

@Test func independentQueueInstancesDoNotLoseConcurrentWrites() async throws {
    let root = FileManager.default.temporaryDirectory.appending(path: UUID().uuidString)
    let file = root.appending(path: "queue.json")
    let appQueue = try EventQueue(fileURL: file)
    let shareQueue = try EventQueue(fileURL: file)

    try await withThrowingTaskGroup(of: Void.self) { group in
        for index in 0 ..< 40 {
            let queue = index.isMultiple(of: 2) ? appQueue : shareQueue
            group.addTask {
                try await queue.enqueue(
                    try MobileEvent(
                        eventID: "event-\(index)",
                        device: MobileDevice(id: "iphone-1", platform: .ios),
                        kind: .text,
                        text: "item \(index)"
                    )
                )
            }
        }
        try await group.waitForAll()
    }

    let ids = Set(try await appQueue.pending().map(\.eventID))
    #expect(ids.count == 40)
}
