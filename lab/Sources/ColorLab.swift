import SwiftUI

/// Swatches with known text/background colours so the `ui color` reader can be
/// validated end-to-end: solid (light/dark), gradient background, low contrast.
struct ColorLab: View {
    var body: some View {
        LabScreen(nav: "color") {
            VStack(spacing: 12) {
                swatch("White on red", fg: .white, bg: .red, id: "color-white-on-red")
                swatch("Red on white", fg: .red, bg: .white, id: "color-red-on-white")
                swatch("Light on dark", fg: Color(white: 0.92), bg: Color(white: 0.08),
                       id: "color-light-on-dark")
                swatch("Green on black", fg: .green, bg: .black, id: "color-green-on-black")
                Text("On gradient")
                    .font(.title3.bold())
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity, minHeight: 48)
                    .background(LinearGradient(
                        colors: [Color(red: 0.16, green: 0.24, blue: 0.86),
                                 Color(red: 0.94, green: 0.82, blue: 0.16)],
                        startPoint: .top, endPoint: .bottom))
                    .accessibilityElement(children: .combine)
                    .accessibilityIdentifier("color-on-gradient")
                swatch("Low contrast", fg: Color(white: 0.66), bg: Color(white: 0.78),
                       id: "color-low-contrast")
                HStack {
                    Text("Has green dot").foregroundColor(.black)
                    Spacer()
                    Circle().fill(.green).frame(width: 18, height: 18)  // minority badge colour
                }
                .padding(.horizontal)
                .frame(maxWidth: .infinity, minHeight: 48)
                .background(Color.white)
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("color-badge-row")
                Spacer()
            }
            .padding()
        }
    }

    private func swatch(_ title: String, fg: Color, bg: Color, id: String) -> some View {
        Text(title)
            .font(.title3.bold())
            .foregroundColor(fg)
            .frame(maxWidth: .infinity, minHeight: 48)
            .background(bg)
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier(id)
    }
}
