import { ChatUI } from '@/components/ChatUI'
import { Card, CardContent } from '@/components/ui/Card'

export function Chat() {
  return (
    <div className="h-[calc(100vh-8rem)] flex flex-col animate-in fade-in duration-300">
      <div className="mb-4">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">AI Assistant</h1>
        <p className="text-gray-500 dark:text-gray-400 mt-1">
          Ask questions about patients, analyze documents, or get AI-assisted insights
        </p>
      </div>

      <Card className="flex-1 flex flex-col overflow-hidden">
        <CardContent className="flex-1 p-0 flex flex-col">
          <ChatUI
            initialMessage="Hello! I'm your AI clinical assistant. Select a patient from the sidebar to ask about their records, or type a command to get started."
          />
        </CardContent>
      </Card>
    </div>
  )
}
