import Foundation

/// Central konfiguration för Puls-AR
/// Ändra serverURL här — alla vyer använder denna automatiskt.
///
/// FÖR PRODUKTION: Byt till https:// och konfigurera SSL på servern.
/// FÖR LOKAL UTVECKLING: Använd http:// och se till att Info.plist
/// har NSAppTransportSecurity → NSAllowsLocalNetworking = YES
enum PulsArConfig {

    /// Backend-serverns bas-URL (utan trailing slash)
    /// Ändra IP-adress om servern kör på en annan maskin.
    static let serverURL = "http://192.168.0.166:8000"

    /// Timeout för vanliga API-anrop (sök, chat) i sekunder
    static let requestTimeout: TimeInterval = 15

    /// Timeout för VPS-lokalisering (snabbare krävs för bra UX)
    static let vpsTimeout: TimeInterval = 5

    /// Timeout för batch-upload (stora filer, kan ta tid)
    static let uploadTimeout: TimeInterval = 120
}
