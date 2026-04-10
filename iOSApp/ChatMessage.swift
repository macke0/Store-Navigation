//
//  ChatMessage.swift
//  PulsAr
//
//  Created by Johan Hartman on 2026-04-07.
//


//
//  ChatView.swift
//  PulsAR
//
//  Claude-powered butiksassistent
//

import SwiftUI
import Combine

// MARK: - Models

struct ChatMessage: Identifiable, Equatable {
    let id = UUID()
    let role: Role
    let content: String
    let timestamp: Date
    
    enum Role {
        case user
        case assistant
    }
}

struct ChatRequest: Codable {
    let meddelande: String
    let session_id: String?
}

struct ChatResponse: Codable {
    let svar: String
    let session_id: String
}

struct SökRequest: Codable {
    let query: String
    let limit: Int?
}

struct SökResponse: Codable {
    let query: String
    let antal: Int
    let resultat: [ProduktMatch]
}

struct ProduktMatch: Codable, Identifiable {
    let id: String
    let namn: String
    let varumarke: String?
    let kategori: String?
    let pris: Double?
    let match_score: Double?
}

// MARK: - Chat Service

@MainActor
class ChatService: ObservableObject {
    static let shared = ChatService()
    
    @Published var messages: [ChatMessage] = []
    @Published var isLoading = false
    @Published var sessionId: String?
    
    private let baseURL: String
    
    init(baseURL: String = PulsArConfig.serverURL) {
        self.baseURL = baseURL
    }
    
    func sendMessage(_ text: String) async {
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        
        // Lägg till användarens meddelande
        let userMessage = ChatMessage(role: .user, content: text, timestamp: Date())
        messages.append(userMessage)
        
        isLoading = true
        
        do {
            let response = try await postChat(meddelande: text)
            
            // Spara session
            sessionId = response.session_id
            
            // Lägg till assistentens svar
            let assistantMessage = ChatMessage(
                role: .assistant,
                content: response.svar,
                timestamp: Date()
            )
            messages.append(assistantMessage)
            
        } catch let error as URLError where error.code == .timedOut {
            let errorMessage = ChatMessage(
                role: .assistant,
                content: "Servern tog för lång tid att svara. Försök igen om en stund.",
                timestamp: Date()
            )
            messages.append(errorMessage)
        } catch let error as URLError where error.code == .cannotConnectToHost || error.code == .notConnectedToInternet {
            let errorMessage = ChatMessage(
                role: .assistant,
                content: "Kan inte nå servern. Kontrollera att backend körs och att du är på rätt nätverk.",
                timestamp: Date()
            )
            messages.append(errorMessage)
        } catch {
            let errorMessage = ChatMessage(
                role: .assistant,
                content: "Något gick fel: \(error.localizedDescription)",
                timestamp: Date()
            )
            messages.append(errorMessage)
        }
        
        isLoading = false
    }
    
    private func postChat(meddelande: String) async throws -> ChatResponse {
        guard let url = URL(string: "\(baseURL)/chat/") else {
            throw URLError(.badURL)
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 30
        
        let body = ChatRequest(meddelande: meddelande, session_id: sessionId)
        request.httpBody = try JSONEncoder().encode(body)
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
        
        return try JSONDecoder().decode(ChatResponse.self, from: data)
    }
    
    /// Snabb sökning utan Claude (gratis, snabbare)
    func quickSearch(_ query: String) async throws -> [ProduktMatch] {
        guard let url = URL(string: "\(baseURL)/chat/sök") else {
            throw URLError(.badURL)
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let body = SökRequest(query: query, limit: 5)
        request.httpBody = try JSONEncoder().encode(body)
        
        let (data, _) = try await URLSession.shared.data(for: request)
        let response = try JSONDecoder().decode(SökResponse.self, from: data)
        
        return response.resultat
    }
    
    func clearChat() {
        messages.removeAll()
        sessionId = nil
    }
}

// MARK: - Chat View

struct ChatView: View {
    @StateObject private var chatService = ChatService.shared
    @State private var inputText = ""
    @FocusState private var isInputFocused: Bool
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            chatHeader
            
            // Messages
            messagesScrollView
            
            // Input
            inputBar
        }
        .background(Color(.systemGroupedBackground))
    }
    
    // MARK: - Header
    
    private var chatHeader: some View {
        HStack {
            Image(systemName: "message.fill")
                .foregroundColor(.blue)
            
            VStack(alignment: .leading, spacing: 2) {
                Text("Butiksassistent")
                    .font(.headline)
                
                Text("Fråga om produkter, alternativ, navigation")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            Spacer()
            
            Button(action: { chatService.clearChat() }) {
                Image(systemName: "trash")
                    .foregroundColor(.secondary)
            }
        }
        .padding()
        .background(Color(.systemBackground))
    }
    
    // MARK: - Messages
    
    private var messagesScrollView: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 12) {
                    // Välkomstmeddelande om tom
                    if chatService.messages.isEmpty {
                        welcomeMessage
                    }
                    
                    // Meddelanden
                    ForEach(chatService.messages) { message in
                        MessageBubble(message: message)
                            .id(message.id)
                    }
                    
                    // Loading indicator
                    if chatService.isLoading {
                        HStack {
                            ProgressView()
                                .padding(.horizontal)
                            Text("Tänker...")
                                .foregroundColor(.secondary)
                            Spacer()
                        }
                        .padding(.horizontal)
                    }
                }
                .padding()
            }
            .onChange(of: chatService.messages.count) { _ in
                if let lastMessage = chatService.messages.last {
                    withAnimation {
                        proxy.scrollTo(lastMessage.id, anchor: .bottom)
                    }
                }
            }
        }
    }
    
    private var welcomeMessage: some View {
        VStack(spacing: 16) {
            Image(systemName: "sparkles")
                .font(.system(size: 48))
                .foregroundColor(.blue)
            
            Text("Hej! Jag hjälper dig hitta produkter.")
                .font(.headline)
            
            Text("Prova att fråga:")
                .font(.subheadline)
                .foregroundColor(.secondary)
            
            VStack(alignment: .leading, spacing: 8) {
                suggestionButton("Var finns mjölk?")
                suggestionButton("Finns något nyttigare än cola?")
                suggestionButton("Laktosfria alternativ")
            }
        }
        .padding(.vertical, 40)
    }
    
    private func suggestionButton(_ text: String) -> some View {
        Button(action: {
            inputText = text
            Task { await chatService.sendMessage(text) }
            inputText = ""
        }) {
            HStack {
                Image(systemName: "text.bubble")
                    .foregroundColor(.blue)
                Text(text)
                    .foregroundColor(.primary)
                Spacer()
                Image(systemName: "arrow.up.circle.fill")
                    .foregroundColor(.blue)
            }
            .padding()
            .background(Color(.systemBackground))
            .cornerRadius(12)
        }
    }
    
    // MARK: - Input Bar
    
    private var inputBar: some View {
        HStack(spacing: 12) {
            TextField("Skriv ett meddelande...", text: $inputText)
                .textFieldStyle(.plain)
                .padding(12)
                .background(Color(.systemBackground))
                .cornerRadius(20)
                .focused($isInputFocused)
                .onSubmit {
                    sendMessage()
                }
            
            Button(action: sendMessage) {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 32))
                    .foregroundColor(inputText.isEmpty ? .gray : .blue)
            }
            .disabled(inputText.isEmpty || chatService.isLoading)
        }
        .padding()
        .background(Color(.secondarySystemBackground))
    }
    
    private func sendMessage() {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        
        inputText = ""
        Task {
            await chatService.sendMessage(text)
        }
    }
}

// MARK: - Message Bubble

struct MessageBubble: View {
    let message: ChatMessage
    
    var body: some View {
        HStack {
            if message.role == .user {
                Spacer(minLength: 60)
            }
            
            VStack(alignment: message.role == .user ? .trailing : .leading, spacing: 4) {
                Text(message.content)
                    .padding(12)
                    .background(bubbleColor)
                    .foregroundColor(textColor)
                    .cornerRadius(16)
                
                Text(timeString)
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
            
            if message.role == .assistant {
                Spacer(minLength: 60)
            }
        }
    }
    
    private var bubbleColor: Color {
        message.role == .user ? .blue : Color(.systemGray5)
    }
    
    private var textColor: Color {
        message.role == .user ? .white : .primary
    }
    
    private var timeString: String {
        let formatter = DateFormatter()
        formatter.timeStyle = .short
        return formatter.string(from: message.timestamp)
    }
}

// MARK: - Preview

struct ChatView_Previews: PreviewProvider {
    static var previews: some View {
        ChatView()
    }
}
