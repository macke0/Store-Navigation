//
//  ContentView 2.swift
//  PulsAr
//
//  Created by Johan Hartman on 2026-03-31.
//


import SwiftUI

struct ContentView: View {
    @State private var visaPersonalmeny = false

    var body: some View {
        NavigationView {
            ZStack {
                Color.black.ignoresSafeArea()

                VStack(spacing: 32) {

                    // Logo och titel
                    VStack(spacing: 12) {
                        ZStack {
                            Circle()
                                .fill(Color.red.opacity(0.15))
                                .frame(width: 100, height: 100)
                            Image(systemName: "cart.fill.badge.plus")
                                .font(.system(size: 44))
                                .foregroundColor(.red)
                        }

                        Text("Puls-AR")
                            .font(.system(size: 42, weight: .bold))
                            .foregroundColor(.white)

                        Text("ICA Maxi Bromma")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                    }
                    .padding(.top, 60)

                    Spacer()

                    // Kundknapp
                    NavigationLink(destination: SökView()) {
                        HStack(spacing: 16) {
                            Image(systemName: "magnifyingglass")
                                .font(.title2)
                                .foregroundColor(.white)
                                .frame(width: 40)
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Hitta en vara")
                                    .font(.headline)
                                    .foregroundColor(.white)
                                Text("Sök och navigera till produkter")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                            Spacer()
                            Image(systemName: "chevron.right")
                                .foregroundColor(.secondary)
                        }
                        .padding()
                        .background(Color.red.opacity(0.15))
                        .cornerRadius(16)
                        .overlay(
                            RoundedRectangle(cornerRadius: 16)
                                .stroke(Color.red.opacity(0.4), lineWidth: 1)
                        )
                    }
                    .padding(.horizontal)

                    // Personalknapp
                    Button {
                        visaPersonalmeny = true
                    } label: {
                        HStack(spacing: 16) {
                            Image(systemName: "person.badge.key.fill")
                                .font(.title2)
                                .foregroundColor(.white)
                                .frame(width: 40)
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Personal")
                                    .font(.headline)
                                    .foregroundColor(.white)
                                Text("Skanna och uppdatera butiken")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                            Spacer()
                            Image(systemName: "chevron.right")
                                .foregroundColor(.secondary)
                        }
                        .padding()
                        .background(Color.blue.opacity(0.15))
                        .cornerRadius(16)
                        .overlay(
                            RoundedRectangle(cornerRadius: 16)
                                .stroke(Color.blue.opacity(0.4), lineWidth: 1)
                        )
                    }
                    .padding(.horizontal)
                    .sheet(isPresented: $visaPersonalmeny) {
                        SkanningMenyView()
                    }

                    Spacer()

                    // Version
                    Text("Puls-AR v1.0")
                        .font(.caption2)
                        .foregroundColor(Color.white.opacity(0.2))
                        .padding(.bottom, 20)
                }
            }
            .navigationBarHidden(true)
        }
    }
}
