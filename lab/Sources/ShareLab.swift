import SwiftUI
import UIKit

/// Presents the real system share sheet from the foreground window, so the lab can act
/// as a generic share origin driven over the CLI (deeplink -> UIActivityViewController).
enum ShareSheet {
    static func present(items: [Any]) {
        guard
            let scene = UIApplication.shared.connectedScenes
                .compactMap({ $0 as? UIWindowScene })
                .first(where: { $0.activationState == .foregroundActive }),
            var top = scene.keyWindow?.rootViewController
        else { return }
        while let presented = top.presentedViewController { top = presented }
        let activity = UIActivityViewController(activityItems: items, applicationActivities: nil)
        if let popover = activity.popoverPresentationController {
            popover.sourceView = top.view
            popover.sourceRect = CGRect(x: top.view.bounds.midX, y: top.view.bounds.midY, width: 1, height: 1)
            popover.permittedArrowDirections = []
        }
        top.present(activity, animated: true)
    }
}

/// The kinds of payload a share deeplink can carry. `text`/`url` travel inside the deeplink;
/// `image`/`file` are synthesized at runtime so nothing needs to be bundled or pre-seeded.
enum ShareType: String, CaseIterable {
    case text, url, image, file
}

private let defaultShareURL = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"

/// A parsed `lazyworker://share?type=<...>&value=<...>` request.
struct ShareRequest: Equatable {
    let raw: String
    let type: ShareType
    let value: String
    let autoPresent: Bool

    static func parse(_ url: URL) -> ShareRequest {
        let query = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
        let typeRaw = query.first { $0.name == "type" }?.value ?? "url"
        let value = query.first { $0.name == "value" }?.value ?? defaultShareURL
        let present = query.first { $0.name == "present" }?.value ?? "auto"
        return ShareRequest(
            raw: url.absoluteString,
            type: ShareType(rawValue: typeRaw) ?? .url,
            value: value,
            autoPresent: present != "manual"
        )
    }

    func activityItems() -> [Any] {
        switch type {
        case .text: return [value]
        case .url: return [URL(string: value) ?? value]
        case .image: return [ShareAssets.image(caption: value)]
        case .file: return [ShareAssets.pdf(text: value)]
        }
    }
}

/// Runtime-generated payloads for image/file shares — deterministic, nothing on disk to seed.
enum ShareAssets {
    static func image(caption: String) -> UIImage {
        let size = CGSize(width: 320, height: 320)
        return UIGraphicsImageRenderer(size: size).image { ctx in
            UIColor.systemIndigo.setFill()
            ctx.fill(CGRect(origin: .zero, size: size))
            (caption as NSString).draw(
                at: CGPoint(x: 24, y: 150),
                withAttributes: [.font: UIFont.boldSystemFont(ofSize: 22), .foregroundColor: UIColor.white]
            )
        }
    }

    static func pdf(text: String) -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("lazyworker-sample.pdf")
        let renderer = UIGraphicsPDFRenderer(bounds: CGRect(x: 0, y: 0, width: 320, height: 320))
        try? renderer.writePDF(to: url) { ctx in
            ctx.beginPage()
            (text as NSString).draw(
                at: CGPoint(x: 24, y: 24),
                withAttributes: [.font: UIFont.systemFont(ofSize: 16)]
            )
        }
        return url
    }
}

/// Holds the pending share request and drives navigation to the share screen on deeplink.
final class ShareRouter: ObservableObject {
    @Published var request: ShareRequest?
    @Published var isPresenting = false

    func receive(_ url: URL) {
        request = ShareRequest.parse(url)
        isPresenting = true
    }
}

/// Dedicated screen shown when a share deeplink arrives: the raw deeplink and the parsed
/// fields at the top, a preview of the payload, and a button that fires the system share sheet.
struct ShareLabView: View {
    let request: ShareRequest?
    @EnvironmentObject var log: EventLog
    @State private var didPresent = false

    var body: some View {
        VStack(spacing: 0) {
            EventLogView()
            if let req = request {
                List {
                    Section("Deeplink") {
                        field("raw", req.raw, id: "share-raw")
                        field("type", req.type.rawValue, id: "share-type")
                        field("value", req.value, id: "share-value")
                    }
                    Section("Preview") { preview(req) }
                }
                Button("Compartilhar") {
                    log.record("share:present:\(req.type.rawValue)")
                    ShareSheet.present(items: req.activityItems())
                }
                .accessibilityIdentifier("share-present")
                .padding()
            } else {
                Text("No share deeplink").padding()
                Spacer()
            }
        }
        .navigationTitle("Share")
        .onAppear {
            guard let req = request else { return }
            log.record("share:\(req.type.rawValue)")
            if req.autoPresent && !didPresent {
                didPresent = true
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
                    ShareSheet.present(items: req.activityItems())
                }
            }
        }
    }

    @ViewBuilder
    private func field(_ key: String, _ value: String, id: String) -> some View {
        HStack(alignment: .top) {
            Text(key).foregroundColor(.secondary)
            Spacer()
            Text(value).multilineTextAlignment(.trailing).accessibilityIdentifier(id)
        }
    }

    @ViewBuilder
    private func preview(_ req: ShareRequest) -> some View {
        switch req.type {
        case .text, .url:
            Text(req.value).accessibilityIdentifier("share-preview")
        case .image:
            Image(uiImage: ShareAssets.image(caption: req.value))
                .resizable().scaledToFit().frame(height: 120)
                .accessibilityIdentifier("share-preview")
        case .file:
            Label("lazyworker-sample.pdf", systemImage: "doc")
                .accessibilityIdentifier("share-preview")
        }
    }
}
