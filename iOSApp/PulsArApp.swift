//
//  PulsArApp.swift
//  PulsAr
//
//  Created by Johan Hartman on 2026-03-31.
//

import SwiftUI

@main
struct PulsArApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    var body: some Scene {
        // Lås ljust läge — kund-UI:t är designat ljust (ICA-vitt). Utan detta
        // flippar systemfärger om telefonen står i mörkt läge och bryter temat.
        WindowGroup { ContentView().preferredColorScheme(.light) }
    }
}

class AppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication,
                     handleEventsForBackgroundURLSession identifier: String,
                     completionHandler: @escaping () -> Void) {
        BackgroundUploadManager.shared.backgroundEventsCompletionHandler = completionHandler
    }
}
