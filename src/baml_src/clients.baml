client<llm> ClaudeClient {
  provider anthropic
  options {
    model "claude-sonnet-4-20250514"
    temperature 0
  }
}

client<llm> GeminiClient {
  provider google-ai
  options {
    model "gemini-2.5-pro"
    temperature 0
  }
}
