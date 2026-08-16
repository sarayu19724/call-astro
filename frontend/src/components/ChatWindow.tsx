import React, { useEffect, useRef } from 'react';
import { User } from 'lucide-react';

interface Message { role: 'user' | 'assistant' | 'system'; content: string; timestamp?: string; }
interface ChatWindowProps { messages: Message[]; isTyping: boolean; language: string; suggestions: string[]; onSuggestionSelect: (q: string) => void; }

const GREETINGS: Record<string, string> = {
  English: '🙏 Namaste! How may I assist you today?',
  Hindi: '🙏 नमस्ते! मैं आपकी क्या सेवा कर सकता हूँ?',
  Hinglish: '🙏 Namaste! Main aapki kya seva kar sakta hoon?',
};

const TypingDots = () => (
  <span className="flex items-center gap-1">
    <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
    <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
    <span className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
  </span>
);

export const ChatWindow: React.FC<ChatWindowProps> = ({ messages, isTyping, language, suggestions, onSuggestionSelect }) => {
  const bottomRef = useRef<HTMLDivElement>(null);
  const greeting = GREETINGS[language] || GREETINGS.Hinglish;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 space-y-6">
      {messages.length === 0 && (
        <div className="flex justify-start max-w-2xl mx-auto">
          <div className="flex gap-4">
            <div className="w-9 h-9 rounded-full bg-amber-500 flex items-center justify-center text-white text-base shadow-sm shrink-0">🔮</div>
            <div className="bg-white border border-slate-200 text-slate-800 rounded-2xl px-5 py-3.5 shadow-sm leading-relaxed">
              {greeting}
            </div>
          </div>
        </div>
      )}

      <div className="max-w-2xl mx-auto space-y-6">
        {messages.map((msg, index) => {
          if (msg.role === 'system') {
            return (
              <div key={index} className="flex justify-center my-2">
                <div className="bg-slate-100 text-slate-500 text-xs px-4 py-1.5 rounded-full">{msg.content}</div>
              </div>
            );
          }

          const isUser = msg.role === 'user';
          const isLastMessage = index === messages.length - 1;
          const isEmptyAssistantPlaceholder = !isUser && msg.content === '' && isLastMessage;

          return (
            <div key={index} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
              <div className={`flex gap-3 max-w-[85%] ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
                <div className={`w-9 h-9 rounded-full flex items-center justify-center text-sm shadow-sm shrink-0 ${isUser ? 'bg-slate-200 text-slate-600' : 'bg-amber-500 text-white'}`}>
                  {isUser ? <User size={16} /> : '🔮'}
                </div>
                <div>
                  <div className={`rounded-2xl px-5 py-3.5 shadow-sm leading-relaxed ${isUser ? 'bg-slate-900 text-white rounded-tr-none' : 'bg-white border border-slate-200 text-slate-800 rounded-tl-none'}`}>
                    {isEmptyAssistantPlaceholder ? (
                      <TypingDots />
                    ) : (
                      <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                    )}
                  </div>
                  {msg.timestamp && !isEmptyAssistantPlaceholder && (
                    <div className={`text-[10px] text-slate-400 mt-1 px-1 ${isUser ? 'text-right' : 'text-left'}`}>
                      {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
        {/* Follow-up suggestion chips after last bot message */}
        {!isTyping && suggestions.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-2 max-w-2xl mx-auto pl-12">
            {suggestions.map((s, i) => (
              <button
                key={i}
                onClick={() => onSuggestionSelect(s)}
                className="px-3 py-1.5 rounded-full text-xs bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-500 hover:text-white hover:border-amber-500 transition-all"
              >
                {s}
              </button>
            ))}
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
};