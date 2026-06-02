import SwiftUI

struct HomeView: View {
    @EnvironmentObject var router: ShareRouter

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                EventLogView()
                List {
                    row("Tap", "link-tap") { TapLab() }
                    row("Wait", "link-wait") { WaitLab() }
                    row("Timing", "link-timing") { TimingLab() }
                    row("Gestures", "link-gesture") { GestureLab() }
                    row("Toggles", "link-toggle") { ToggleLab() }
                    row("Type", "link-type") { TypeLab() }
                    row("Scroll", "link-scroll") { ScrollLab() }
                    row("Scroll To", "link-scrollto") { ScrollToLab() }
                    row("Screenshot", "link-screenshot") { ScreenshotLab() }
                    row("Card", "link-card") { CardLab() }
                    row("OCR", "link-ocr") { OcrLab() }
                    row("Ambiguity", "link-ambiguity") { AmbiguityLab() }
                    row("Combined Flow", "link-combined") { CombinedFlowLab() }
                    row("Batch Flow", "link-batch") { BatchFlowLab() }
                }
            }
            .navigationTitle("LazyWorker Lab")
            .navigationDestination(isPresented: $router.isPresenting) {
                ShareLabView(request: router.request)
            }
        }
    }

    @ViewBuilder
    private func row<Destination: View>(
        _ title: String,
        _ identifier: String,
        @ViewBuilder destination: () -> Destination
    ) -> some View {
        NavigationLink(destination: destination()) {
            Text(title)
        }
        .accessibilityIdentifier(identifier)
    }
}
