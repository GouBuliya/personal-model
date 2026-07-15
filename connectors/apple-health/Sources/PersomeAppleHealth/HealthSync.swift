import Foundation

struct AnchoredHealthPage<Anchor> {
    let events: [HealthEvent]
    let deletedEvents: [HealthEventDeletion]
    let nextAnchor: Anchor?
    let hasMore: Bool
}

func synchronizeAnchoredHealthPages<Anchor>(
    initialAnchor: Anchor?,
    fetch: (Anchor?) async throws -> AnchoredHealthPage<Anchor>,
    upload: ([HealthEvent], [HealthEventDeletion]) async throws -> HealthImportResult,
    persist: (Anchor?) throws -> Void
) async throws -> HealthImportResult {
    var anchor = initialAnchor
    var totals = HealthImportResult.zero

    while true {
        let page = try await fetch(anchor)
        if !page.events.isEmpty || !page.deletedEvents.isEmpty {
            let result = try await upload(page.events, page.deletedEvents)
            totals = totals.adding(result)
        }
        try persist(page.nextAnchor)
        anchor = page.nextAnchor
        if !page.hasMore { return totals }
    }
}

extension HealthImportResult {
    static let zero = Self(
        schemaVersion: 1,
        received: 0,
        inserted: 0,
        corrected: 0,
        duplicates: 0,
        deleted: 0
    )

    func adding(_ other: Self) -> Self {
        Self(
            schemaVersion: schemaVersion,
            received: received + other.received,
            inserted: inserted + other.inserted,
            corrected: corrected + other.corrected,
            duplicates: duplicates + other.duplicates,
            deleted: deleted + other.deleted
        )
    }
}
