import SwiftUI

struct ContentView: View {
    @State private var visaPersonalmeny = false
    @State private var animateIn = false

    private let icaRöd = Color(red: 0.89, green: 0.12, blue: 0.17)
    private let icaMörkRöd = Color(red: 0.72, green: 0.08, blue: 0.12)

    var body: some View {
        NavigationView {
            ZStack {
                // Bakgrund
                Color.black.ignoresSafeArea()

                // Bakgrund - mörk gradient med röd accent
                LinearGradient(
                    colors: [
                        Color(red: 0.35, green: 0.05, blue: 0.05),
                        Color(red: 0.15, green: 0.02, blue: 0.02),
                        .black
                    ],
                    startPoint: .top,
                    endPoint: .center
                )
                .ignoresSafeArea()

                // Gradient overlay
                VStack {
                    Spacer()
                        .frame(height: 150)
                    LinearGradient(
                        colors: [
                            .black.opacity(0.0),
                            .black.opacity(0.7),
                            .black.opacity(0.95),
                            .black
                        ],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                }
                .ignoresSafeArea()

                // Innehåll
                VStack(spacing: 0) {
                    Spacer()

                    // Logo & titel
                    VStack(spacing: 16) {
                        ZStack {
                            RoundedRectangle(cornerRadius: 22)
                                .fill(
                                    LinearGradient(
                                        colors: [icaRöd, icaMörkRöd],
                                        startPoint: .topLeading,
                                        endPoint: .bottomTrailing
                                    )
                                )
                                .frame(width: 74, height: 74)
                                .shadow(color: icaRöd.opacity(0.4), radius: 16, y: 6)

                            Image(systemName: "cart.fill")
                                .font(.system(size: 32, weight: .medium))
                                .foregroundColor(.white)
                        }
                        .opacity(animateIn ? 1 : 0)
                        .offset(y: animateIn ? 0 : 20)

                        VStack(spacing: 6) {
                            Text("Puls-AR")
                                .font(.system(size: 36, weight: .bold, design: .rounded))
                                .foregroundColor(.white)

                            Text("ICA Maxi Bromma")
                                .font(.system(size: 13, weight: .semibold))
                                .foregroundColor(.white.opacity(0.5))
                                .tracking(2)
                                .textCase(.uppercase)
                        }
                        .opacity(animateIn ? 1 : 0)
                        .offset(y: animateIn ? 0 : 15)
                    }
                    .padding(.bottom, 44)

                    // Knappar
                    VStack(spacing: 12) {
                        // Sök-knapp
                        NavigationLink(destination: SökView()) {
                            HStack(spacing: 12) {
                                Image(systemName: "magnifyingglass")
                                    .font(.system(size: 16, weight: .bold))
                                    .foregroundColor(.white)

                                Text("Hitta en vara")
                                    .font(.system(size: 16, weight: .bold, design: .rounded))
                                    .foregroundColor(.white)

                                Spacer()

                                Image(systemName: "chevron.right")
                                    .font(.system(size: 13, weight: .bold))
                                    .foregroundColor(.white.opacity(0.6))
                            }
                            .padding(.horizontal, 20)
                            .padding(.vertical, 16)
                            .background(
                                LinearGradient(
                                    colors: [icaRöd, icaMörkRöd],
                                    startPoint: .leading,
                                    endPoint: .trailing
                                )
                            )
                            .cornerRadius(14)
                            .shadow(color: icaRöd.opacity(0.35), radius: 10, y: 4)
                        }
                        .opacity(animateIn ? 1 : 0)
                        .offset(y: animateIn ? 0 : 20)

                        // Personal-knapp
                        Button { visaPersonalmeny = true } label: {
                            HStack(spacing: 12) {
                                Image(systemName: "person.badge.key.fill")
                                    .font(.system(size: 16, weight: .bold))
                                    .foregroundColor(.white.opacity(0.8))

                                Text("Personal")
                                    .font(.system(size: 16, weight: .bold, design: .rounded))
                                    .foregroundColor(.white.opacity(0.8))

                                Spacer()

                                Image(systemName: "chevron.right")
                                    .font(.system(size: 13, weight: .bold))
                                    .foregroundColor(.white.opacity(0.3))
                            }
                            .padding(.horizontal, 20)
                            .padding(.vertical, 16)
                            .background(.ultraThinMaterial)
                            .cornerRadius(14)
                            .overlay(
                                RoundedRectangle(cornerRadius: 14)
                                    .stroke(.white.opacity(0.1), lineWidth: 1)
                            )
                        }
                        .sheet(isPresented: $visaPersonalmeny) {
                            SkanningMenyView()
                        }
                        .opacity(animateIn ? 1 : 0)
                        .offset(y: animateIn ? 0 : 20)
                    }
                    .padding(.horizontal, 36)

                    Spacer()
                        .frame(height: 50)

                    Text("v1.0")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(.white.opacity(0.15))
                        .padding(.bottom, 12)
                }
            }
            .navigationBarHidden(true)
            .onAppear {
                withAnimation(.easeOut(duration: 0.8)) {
                    animateIn = true
                }
            }
        }
    }
}

#Preview {
    ContentView()
}
