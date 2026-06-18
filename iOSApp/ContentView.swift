import SwiftUI

struct ContentView: View {
    @State private var visaPersonalmeny = false
    @State private var animateIn = false

    var body: some View {
        NavigationView {
            ZStack {
                Tema.bakgrund.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 24) {
                        rubrik
                            .padding(.top, 24)

                        // Hjälte: Matinspiration — appens starkaste, mest visuella flöde.
                        NavigationLink(destination: MaträttView()) {
                            hjälteKort
                        }
                        .buttonStyle(TryckStyle())
                        .opacity(animateIn ? 1 : 0)
                        .offset(y: animateIn ? 0 : 24)

                        VStack(spacing: 12) {
                            // Varusökning = hitta en specifik vara och navigera dit.
                            NavigationLink(destination: KundAssistentView()) {
                                radKort(
                                    ikon: "magnifyingglass",
                                    titel: "Hitta en vara",
                                    undertitel: "Sök & navigera till varor i butiken",
                                    accent: Tema.röd
                                )
                            }
                            .buttonStyle(TryckStyle())

                            // Personal = butiksskanning (separat från kundsidan).
                            Button {
                                Haptik.tryck()
                                visaPersonalmeny = true
                            } label: {
                                radKort(
                                    ikon: "person.badge.key.fill",
                                    titel: "Personal",
                                    undertitel: "Skanna & bygg butikskartan",
                                    accent: Tema.textSvag
                                )
                            }
                            .buttonStyle(TryckStyle())
                            .sheet(isPresented: $visaPersonalmeny) {
                                SkanningMenyView()
                            }
                        }
                        .opacity(animateIn ? 1 : 0)
                        .offset(y: animateIn ? 0 : 24)

                        Text("v1.0")
                            .font(Tema.Typ.liten)
                            .foregroundColor(Tema.textTunn)
                            .padding(.top, 8)
                    }
                    .padding(.horizontal, 20)
                    .padding(.bottom, 40)
                }
            }
            .navigationBarHidden(true)
            .onAppear {
                withAnimation(.spring(response: 0.6, dampingFraction: 0.8)) {
                    animateIn = true
                }
            }
        }
        .navigationViewStyle(.stack)
    }

    // MARK: Rubrik

    private var rubrik: some View {
        VStack(spacing: 14) {
            ZStack {
                RoundedRectangle(cornerRadius: 20)
                    .fill(
                        LinearGradient(colors: [Tema.röd, Tema.mörkRöd],
                                       startPoint: .topLeading, endPoint: .bottomTrailing)
                    )
                    .frame(width: 68, height: 68)
                    .shadow(color: Tema.röd.opacity(0.35), radius: 14, y: 6)
                Image(systemName: "cart.fill")
                    .font(.system(size: 30, weight: .medium))
                    .foregroundColor(.white)
            }
            .opacity(animateIn ? 1 : 0)
            .offset(y: animateIn ? 0 : 16)

            VStack(spacing: 4) {
                Text("Puls-AR")
                    .font(Tema.Typ.display)
                    .foregroundColor(Tema.text)
                Text("ICA MAXI BROMMA")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(Tema.textSvag)
                    .tracking(2)
            }
            .opacity(animateIn ? 1 : 0)
            .offset(y: animateIn ? 0 : 12)
        }
    }

    // MARK: Hjälte-kort

    private var hjälteKort: some View {
        // Magasin-stil: hög bildyta med titeln OVANPÅ via mörk scrim, en liten
        // kategori-pill uppe till vänster. Aptitlig varm gradient som "foto" tills
        // riktiga rättbilder bundlas.
        ZStack(alignment: .bottomLeading) {
            LinearGradient(
                colors: [
                    Color(red: 0.97, green: 0.45, blue: 0.20),
                    Color(red: 0.95, green: 0.30, blue: 0.16),
                    Tema.mörkRöd
                ],
                startPoint: .topLeading, endPoint: .bottomTrailing
            )
            // Dekorativa symboler högt upp, dämpade så de inte konkurrerar med titeln.
            Image(systemName: "fork.knife")
                .font(.system(size: 110, weight: .bold))
                .foregroundColor(.white.opacity(0.10))
                .rotationEffect(.degrees(-12))
                .offset(x: 150, y: -36)

            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 5) {
                    Image(systemName: "sparkles").font(.system(size: 10, weight: .bold))
                    Text("DAGENS KAMPANJER").font(.system(size: 10, weight: .heavy)).tracking(1.2)
                }
                .foregroundColor(.white)
                .padding(.horizontal, 10).padding(.vertical, 5)
                .background(.white.opacity(0.22))
                .clipShape(Capsule())

                Spacer()

                Text("Matinspiration")
                    .font(.system(size: 26, weight: .heavy, design: .rounded))
                    .foregroundColor(.white)
                Text("Recept & erbjudanden — med priser och besparing")
                    .font(Tema.Typ.under)
                    .foregroundColor(.white.opacity(0.92))
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)
            }
            .padding(18)
        }
        .frame(height: 200)
        .frame(maxWidth: .infinity, alignment: .leading)
        .bildScrim(hörn: 24)
        .overlay(RoundedRectangle(cornerRadius: 24).stroke(Tema.kortKant, lineWidth: 1))
        .shadow(color: Tema.röd.opacity(0.28), radius: 18, y: 8)
    }

    // MARK: Rad-kort

    private func radKort(ikon: String, titel: String, undertitel: String, accent: Color) -> some View {
        HStack(spacing: 14) {
            ZStack {
                RoundedRectangle(cornerRadius: 12)
                    .fill(accent.opacity(0.12))
                    .frame(width: 44, height: 44)
                Image(systemName: ikon)
                    .font(.system(size: 18, weight: .bold))
                    .foregroundColor(accent)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(titel)
                    .font(Tema.Typ.titel)
                    .foregroundColor(Tema.text)
                Text(undertitel)
                    .font(Tema.Typ.under)
                    .foregroundColor(Tema.textSvag)
            }
            Spacer()
            Image(systemName: "chevron.right")
                .font(.system(size: 13, weight: .bold))
                .foregroundColor(Tema.textTunn)
        }
        .padding(14)
        .kortYta()
    }
}

/// Direkt-känsla vid tryck: liten skala + haptik så knappen svarar omedelbart.
struct TryckStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .animation(.spring(response: 0.3, dampingFraction: 0.7), value: configuration.isPressed)
            .onChange(of: configuration.isPressed) { _, nytt in
                if nytt { Haptik.tryck() }
            }
    }
}

#Preview {
    ContentView()
}
