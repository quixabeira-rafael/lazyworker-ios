import SwiftUI

/// Exercises distinct temporal responses to a single tap so the steady-state
/// detector can be validated against immediate, delayed, animated, staged and
/// never-settling behaviors.
struct TimingLab: View {
    @State private var phase = 0
    @State private var spinning = false
    @State private var progress = 0.0
    @State private var color = Color.gray

    var body: some View {
        LabScreen(nav: "timing") {
            VStack(spacing: 12) {
                ZStack {
                    RoundedRectangle(cornerRadius: 16).fill(color)
                    if spinning {
                        ProgressView().scaleEffect(2.0).tint(.white)
                    }
                    Text("phase \(phase)")
                        .font(.largeTitle.bold())
                        .foregroundStyle(.white)
                        .accessibilityIdentifier("timing-phase")
                }
                .frame(height: 180)

                ProgressView(value: progress)
                    .accessibilityIdentifier("timing-progress-bar")

                Button("Instant") { reset(); color = .green; phase = 1 }
                    .accessibilityIdentifier("timing-instant")
                Button("Delayed 1.5s") {
                    reset()
                    DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
                        color = .blue; phase = 1
                    }
                }
                .accessibilityIdentifier("timing-delayed")
                Button("Spinner then content 2s") {
                    reset(); spinning = true
                    DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                        spinning = false; color = .purple; phase = 1
                    }
                }
                .accessibilityIdentifier("timing-spinner")
                Button("Progress fill 2s") {
                    reset()
                    withAnimation(.linear(duration: 2.0)) { progress = 1.0 }
                    DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                        color = .orange; phase = 1
                    }
                }
                .accessibilityIdentifier("timing-progress")
                Button("Staged 4 steps") {
                    reset()
                    let palette: [Color] = [.red, .orange, .yellow, .green]
                    for (i, c) in palette.enumerated() {
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4 * Double(i + 1)) {
                            color = c; phase = i + 1
                        }
                    }
                }
                .accessibilityIdentifier("timing-staged")
                Button("Infinite spinner") { reset(); spinning = true }
                    .accessibilityIdentifier("timing-infinite")
                Button("Reset") { reset() }
                    .accessibilityIdentifier("timing-reset")
                Spacer()
            }
            .padding()
        }
    }

    private func reset() {
        spinning = false
        progress = 0.0
        color = .gray
        phase = 0
    }
}
