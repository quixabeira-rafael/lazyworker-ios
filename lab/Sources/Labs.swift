import SwiftUI

struct TapLab: View {
    @EnvironmentObject var log: EventLog

    var body: some View {
        LabScreen(nav: "tap") {
            VStack(spacing: 16) {
                Button("Primary") { log.record("tap:btn-primary") }
                    .accessibilityIdentifier("btn-primary")
                Button("Secondary") { log.record("tap:btn-secondary") }
                    .accessibilityIdentifier("btn-secondary")
                Button("Disabled") { log.record("tap:btn-disabled") }
                    .disabled(true)
                    .accessibilityIdentifier("btn-disabled")
                Spacer()
            }
            .padding()
        }
    }
}

struct GestureLab: View {
    @EnvironmentObject var log: EventLog

    var body: some View {
        LabScreen(nav: "gesture") {
            VStack {
                Text("Gesture Target")
                    .frame(maxWidth: .infinity)
                    .padding(40)
                    .background(Color.blue.opacity(0.2))
                    .accessibilityIdentifier("btn-gesture")
                    .onTapGesture(count: 2) { log.record("double_tap:btn-gesture") }
                    .onLongPressGesture { log.record("long_press:btn-gesture") }
                Spacer()
            }
            .padding()
        }
    }
}

struct ToggleLab: View {
    @EnvironmentObject var log: EventLog
    @State private var on = false
    @State private var slider = 0.0

    var body: some View {
        LabScreen(nav: "toggle") {
            VStack(spacing: 24) {
                HStack {
                    Text("Switch")
                    Spacer()
                    Toggle("", isOn: $on)
                        .labelsHidden()
                        .accessibilityIdentifier("switch-1")
                        .onChange(of: on) { value in
                            log.record("toggled:switch-1=\(value ? "on" : "off")")
                        }
                }
                Slider(value: $slider, in: 0...5, step: 1)
                    .accessibilityIdentifier("slider-1")
                    .onChange(of: slider) { value in
                        log.record("slid:slider-1=\(Int(value))")
                    }
                Spacer()
            }
            .padding()
        }
    }
}

struct TypeLab: View {
    @EnvironmentObject var log: EventLog
    @State private var name = ""
    @State private var secret = ""

    var body: some View {
        LabScreen(nav: "type") {
            VStack(spacing: 16) {
                TextField("Name", text: $name)
                    .textFieldStyle(.roundedBorder)
                    .accessibilityIdentifier("field-name")
                    .onChange(of: name) { value in
                        log.record(value.isEmpty ? "cleared:field-name" : "typed:\(value)")
                    }
                Text(name).accessibilityIdentifier("field-name-mirror")
                Button("Clear") { name = "" }
                    .accessibilityIdentifier("btn-clear-name")
                SecureField("Secret", text: $secret)
                    .textFieldStyle(.roundedBorder)
                    .accessibilityIdentifier("field-secret")
                    .onChange(of: secret) { value in log.record("typed_secure:\(value.count)") }
                Spacer()
            }
            .padding()
        }
    }
}

struct ScrollLab: View {
    var body: some View {
        LabScreen(nav: "scroll") {
            ScrollView(.vertical) {
                VStack(spacing: 0) {
                    Text("SCROLL-TOP")
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color.green.opacity(0.3))
                        .accessibilityIdentifier("marker-top")
                    Color.clear.frame(height: 1400)
                    Text("SCROLL-BOTTOM")
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color.orange.opacity(0.3))
                        .accessibilityIdentifier("marker-bottom")
                }
            }
        }
    }
}

struct ScrollToLab: View {
    @EnvironmentObject var log: EventLog

    var body: some View {
        LabScreen(nav: "scrollto") {
            List(0..<60) { index in
                Text("Row \(index)")
                    .accessibilityIdentifier("row-\(index)")
                    .onAppear { if index == 50 { log.record("scrolled_to:row-50") } }
            }
        }
    }
}

struct ScreenshotLab: View {
    var body: some View {
        LabScreen(nav: "screenshot") {
            VStack {
                Spacer()
                Text("LWLAB-SCREENSHOT-MARKER")
                    .font(.title.bold())
                    .foregroundStyle(.white)
                    .padding(40)
                    .background(Color.red)
                    .accessibilityIdentifier("screenshot-marker")
                Spacer()
            }
        }
    }
}

struct AmbiguityLab: View {
    @EnvironmentObject var log: EventLog

    var body: some View {
        LabScreen(nav: "ambiguity") {
            VStack(spacing: 16) {
                Button("Twin") { log.record("tap:twin#1") }
                    .accessibilityIdentifier("twin-a")
                Button("Twin") { log.record("tap:twin#2") }
                    .accessibilityIdentifier("twin-b")
                Spacer()
            }
            .padding()
        }
    }
}

struct CombinedFlowLab: View {
    @EnvironmentObject var log: EventLog
    @State private var user = ""
    @State private var pass = ""
    @State private var result = ""

    var body: some View {
        LabScreen(nav: "combined") {
            VStack(spacing: 16) {
                TextField("User", text: $user)
                    .textFieldStyle(.roundedBorder)
                    .accessibilityIdentifier("field-user")
                SecureField("Pass", text: $pass)
                    .textFieldStyle(.roundedBorder)
                    .accessibilityIdentifier("field-pass")
                Button("Submit") {
                    let ok = !user.isEmpty && !pass.isEmpty
                    result = ok ? "WELCOME" : ""
                    log.record("submitted:login=\(ok ? "ok" : "err")")
                }
                .accessibilityIdentifier("btn-submit")
                Text(result).accessibilityIdentifier("result-banner")
                Spacer()
            }
            .padding()
        }
    }
}

struct BatchFlowLab: View {
    @EnvironmentObject var log: EventLog
    @State private var user = ""
    @State private var pass = ""
    @State private var result = ""

    var body: some View {
        LabScreen(nav: "batch") {
            VStack(spacing: 16) {
                TextField("User", text: $user)
                    .textFieldStyle(.roundedBorder)
                    .accessibilityIdentifier("field-user")
                SecureField("Pass", text: $pass)
                    .textFieldStyle(.roundedBorder)
                    .accessibilityIdentifier("field-pass")
                Button("Submit") {
                    let ok = !user.isEmpty && !pass.isEmpty
                    result = ok ? "submitted:login=ok" : "submitted:login=err"
                    log.record(result)
                }
                .accessibilityIdentifier("btn-submit")
                Text(result).accessibilityIdentifier("batch-result")
                Spacer()
            }
            .padding()
        }
    }
}
