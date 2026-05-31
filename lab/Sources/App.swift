import SwiftUI

/// Single source of truth: every action records a canonical "verb:target" string
/// that the e2e harness reads back from the `event-log` accessibility node.
final class EventLog: ObservableObject {
    @Published var last: String = "ready"

    func record(_ event: String) {
        last = event
    }
}

/// The one node every assertion reads. Present at the top of every screen.
struct EventLogView: View {
    @EnvironmentObject var log: EventLog

    var body: some View {
        Text(log.last)
            .font(.footnote.monospaced())
            .padding(8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(.secondarySystemBackground))
            .accessibilityIdentifier("event-log")
    }
}

/// Wraps a lab screen with the event log and records a `nav:<screen>` event on appear.
struct LabScreen<Content: View>: View {
    let nav: String
    @ViewBuilder var content: Content
    @EnvironmentObject var log: EventLog

    var body: some View {
        VStack(spacing: 0) {
            EventLogView()
            content
        }
        .onAppear { log.record("nav:\(nav)") }
    }
}

@main
struct LazyWorkerLabApp: App {
    @StateObject private var log = EventLog()

    var body: some Scene {
        WindowGroup {
            HomeView()
                .environmentObject(log)
                .onOpenURL { url in
                    log.record("deeplink:\(url.host ?? "")\(url.path)")
                }
        }
    }
}
