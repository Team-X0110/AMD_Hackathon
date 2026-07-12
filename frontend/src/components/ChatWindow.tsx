import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { getFirebase } from '../firebase';
import { ref, push, set, remove, update, onValue } from 'firebase/database';
import { 
  Trash2, Edit2, Check, X, 
  Smile, MessageCircle, 
  Search, ArrowDown, Trash, Terminal, Send, Zap
} from 'lucide-react';
import { format } from 'date-fns';

interface Message {
  id: string;
  text: string;
  senderId: string;
  senderName: string;
  senderAvatarColor: string;
  timestamp: number;
  edited?: boolean;
}

interface ChatWindowProps {
  activeChatId: string | null;
}

const QUICK_EMOJIS = ['👍', '✅', '❌', '⚠️', '💡', '🚀', '🔍', '⚙️'];

export const ChatWindow: React.FC<ChatWindowProps> = ({ activeChatId }) => {
  const { currentUser, profileData } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState('');
  const [dbInstance, setDbInstance] = useState<any>(null);
  const [chatName, setChatName] = useState('Session');

  const [isRenamingChat, setIsRenamingChat] = useState(false);
  const [newChatName, setNewChatName] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [editingMessageText, setEditingMessageText] = useState('');
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const [showScrollDown, setShowScrollDown] = useState(false);

  useEffect(() => {
    try {
      const { db } = getFirebase();
      setDbInstance(db);
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => {
    if (!dbInstance || !activeChatId) return;
    const chatRef = ref(dbInstance, `chats/${activeChatId}`);
    const unsubscribe = onValue(chatRef, (snapshot) => {
      const data = snapshot.val();
      if (data) setChatName(data.name || 'Session');
    });
    return () => unsubscribe();
  }, [dbInstance, activeChatId]);

  useEffect(() => {
    if (!dbInstance || !activeChatId) return;
    const messagesRef = ref(dbInstance, `messages/${activeChatId}`);
    const unsubscribe = onValue(messagesRef, (snapshot) => {
      const data = snapshot.val();
      if (data) {
        const msgs = Object.keys(data).map(key => data[key]) as Message[];
        msgs.sort((a, b) => a.timestamp - b.timestamp);
        setMessages(msgs);
        setTimeout(() => scrollToBottom('auto'), 50);
      } else {
        setMessages([]);
      }
    });
    return () => unsubscribe();
  }, [dbInstance, activeChatId]);

  const scrollToBottom = (behavior: ScrollBehavior = 'smooth') => {
    messagesEndRef.current?.scrollIntoView({ behavior });
  };

  const handleScroll = () => {
    if (!messagesContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = messagesContainerRef.current;
    setShowScrollDown(scrollHeight - scrollTop - clientHeight > 100);
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim() || !dbInstance || !activeChatId || !currentUser) return;

    try {
      const messagesRef = ref(dbInstance, `messages/${activeChatId}`);
      const newMessageRef = push(messagesRef);
      const messageId = newMessageRef.key;

      if (messageId) {
        const newMessage: Message = {
          id: messageId,
          text: inputText.trim(),
          senderId: currentUser.uid,
          senderName: profileData?.displayName || 'Unknown',
          senderAvatarColor: profileData?.avatarColor || 'from-neutral-500 to-neutral-700',
          timestamp: Date.now()
        };

        await set(newMessageRef, newMessage);
        await update(ref(dbInstance, `chats/${activeChatId}`), {
          lastMessage: inputText.trim(),
          lastMessageTime: Date.now()
        });

        setInputText('');
        setShowEmojiPicker(false);
        setTimeout(() => scrollToBottom('smooth'), 50);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleClearChat = async () => {
    if (!dbInstance || !activeChatId) return;
    if (confirm('Flush all session messages?')) {
      try {
        await remove(ref(dbInstance, `messages/${activeChatId}`));
        await update(ref(dbInstance, `chats/${activeChatId}`), { lastMessage: 'Log cleared.', lastMessageTime: Date.now() });
      } catch (e) { console.error(e); }
    }
  };

  const handleRenameChat = async () => {
    if (!dbInstance || !activeChatId || !newChatName.trim()) return;
    try {
      await update(ref(dbInstance, `chats/${activeChatId}`), { name: newChatName.trim() });
      setIsRenamingChat(false);
    } catch (e) { console.error(e); }
  };

  const handleDeleteMessage = async (messageId: string) => {
    if (!dbInstance || !activeChatId) return;
    if (confirm('Delete this message?')) {
      try {
        await remove(ref(dbInstance, `messages/${activeChatId}/${messageId}`));
        if (messages.length > 0 && messages[messages.length - 1].id === messageId) {
          const prevMsg = messages.length > 1 ? messages[messages.length - 2].text : 'Log cleared.';
          await update(ref(dbInstance, `chats/${activeChatId}`), { lastMessage: prevMsg });
        }
      } catch (e) { console.error(e); }
    }
  };

  const handleEditMessageSubmit = async (messageId: string) => {
    if (!dbInstance || !activeChatId || !editingMessageText.trim()) return;
    try {
      await update(ref(dbInstance, `messages/${activeChatId}/${messageId}`), { text: editingMessageText.trim(), edited: true });
      if (messages.length > 0 && messages[messages.length - 1].id === messageId) {
        await update(ref(dbInstance, `chats/${activeChatId}`), { lastMessage: editingMessageText.trim() });
      }
      setEditingMessageId(null);
    } catch (e) { console.error(e); }
  };

  const addEmoji = (emoji: string) => setInputText(prev => prev + emoji);

  const getGroupedMessages = () => {
    const groups: { [key: string]: Message[] } = {};
    const filtered = searchQuery.trim()
      ? messages.filter(m => m.text.toLowerCase().indexOf(searchQuery.toLowerCase()) !== -1)
      : messages;
    filtered.forEach((msg) => {
      const dateKey = format(msg.timestamp, 'MMMM d, yyyy');
      if (!groups[dateKey]) groups[dateKey] = [];
      groups[dateKey].push(msg);
    });
    return groups;
  };

  const groupedMessages = getGroupedMessages();

  // Welcome dashboard when no chat selected
  if (!activeChatId) {
    return (
      <div className="flex-1 h-full bg-blue-50 dark:bg-dark-bg flex flex-col items-center justify-center p-8 text-center relative overflow-hidden transition-colors">
        {/* Decorative grid background */}
        <div className="absolute inset-0 bg-[linear-gradient(rgba(139,92,246,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(139,92,246,0.03)_1px,transparent_1px)] bg-[size:32px_32px] dark:bg-[linear-gradient(rgba(139,92,246,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(139,92,246,0.05)_1px,transparent_1px)]" />
        {/* Radial glow */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 rounded-full bg-brand opacity-5 blur-3xl pointer-events-none" />

        <div className="max-w-lg space-y-6 relative z-10 w-full">
          {/* Animated icon ring */}
          <div className="flex items-center justify-center mb-2">
            <div className="relative">
              <div className="w-24 h-24 rounded-full border-2 border-brand/20 flex items-center justify-center animate-pulse-ring">
                <div className="w-16 h-16 rounded-full border border-brand/30 flex items-center justify-center bg-brand/5">
                  <Terminal size={32} className="text-brand" />
                </div>
              </div>
            </div>
          </div>

          <div className="border border-light-border dark:border-dark-border bg-light-surface/80 dark:bg-dark-surface/80 backdrop-blur-sm p-10 rounded-2xl shadow-xl dark:shadow-brand/5 flex flex-col items-center">
            <h2 className="text-2xl font-extrabold tracking-wide text-neutral-900 dark:text-white uppercase mb-3">
              AMD Core Standby
            </h2>
            <p className="text-neutral-500 dark:text-neutral-400 text-sm leading-relaxed mb-8 max-w-md mx-auto">
              Awaiting connection. Select or initiate an orchestration session from the sidebar to activate the localized LLM pipeline.
            </p>
            
            {/* Status pills */}
            <div className="flex gap-3 flex-wrap justify-center mb-8">
              <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-green-500/10 border border-green-500/20 text-green-600 dark:text-green-400 text-xs font-semibold">
                <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" /> Engine Online
              </span>
              <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-brand/10 border border-brand/20 text-brand text-xs font-semibold">
                <Zap size={11} /> AMD ROCm Active
              </span>
            </div>

            <div className="w-full flex justify-between items-center text-xs font-mono text-neutral-400 dark:text-neutral-600 border-t border-neutral-200 dark:border-neutral-800 pt-4 uppercase tracking-wider">
              <span>Status: Awaiting Input</span>
              <span>Engine: Standby</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 h-full bg-light-bg dark:bg-dark-bg flex flex-col justify-between relative transition-colors">

      {/* Chat Header */}
      <div className="h-16 border-b border-light-border dark:border-dark-border bg-light-surface dark:bg-dark-surface px-5 flex items-center justify-between shrink-0 z-10 transition-colors shadow-sm">
        <div className="flex items-center gap-3.5 min-w-0">
          {/* Avatar with brand gradient */}
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand to-brand-hover flex items-center justify-center text-white text-sm font-extrabold shrink-0 shadow-md shadow-brand/30">
            {chatName.charAt(0).toUpperCase()}
          </div>
          <div className="min-w-0">
            {isRenamingChat ? (
              <div className="flex items-center gap-1.5">
                <input
                  type="text" value={newChatName}
                  onChange={(e) => setNewChatName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleRenameChat(); if (e.key === 'Escape') setIsRenamingChat(false); }}
                  className="text-sm px-3 py-1.5 rounded-lg bg-light-surface dark:bg-dark-card border border-brand text-neutral-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-brand/20"
                  autoFocus
                />
                <button onClick={handleRenameChat} className="text-green-500 hover:text-green-400 p-1.5 rounded-lg hover:bg-green-500/10 transition-colors cursor-pointer"><Check size={15} /></button>
                <button onClick={() => setIsRenamingChat(false)} className="text-neutral-400 hover:text-red-500 p-1.5 rounded-lg hover:bg-red-500/10 transition-colors cursor-pointer"><X size={15} /></button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <h3
                  className="font-bold text-neutral-900 dark:text-white truncate text-base hover:text-brand dark:hover:text-brand cursor-pointer transition-colors"
                  onClick={() => { setIsRenamingChat(true); setNewChatName(chatName); }} title="Rename Session"
                >
                  {chatName}
                </h3>
                <button onClick={() => { setIsRenamingChat(true); setNewChatName(chatName); }} className="text-neutral-400 hover:text-neutral-900 dark:hover:text-white transition-colors p-0.5 cursor-pointer opacity-0 group-hover:opacity-100">
                  <Edit2 size={12} />
                </button>
              </div>
            )}
            {/* Active status pill */}
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand opacity-60"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-brand"></span>
              </span>
              <span className="text-[10px] text-neutral-500 dark:text-neutral-500 font-mono tracking-widest uppercase">Pipeline Active</span>
            </div>
          </div>
        </div>

        {/* Header Actions */}
        <div className="flex items-center gap-2">
          <div className="flex items-center">
            {isSearching ? (
              <div className="flex items-center gap-2 bg-light-card dark:bg-dark-card border border-light-border dark:border-dark-border rounded-xl px-3 py-2 text-sm">
                <Search size={13} className="text-neutral-400 shrink-0" />
                <input
                  type="text" value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search messages..."
                  className="bg-transparent text-neutral-900 dark:text-white focus:outline-none placeholder:text-neutral-400 w-36 md:w-48 text-sm"
                  autoFocus
                />
                <button onClick={() => { setSearchQuery(''); setIsSearching(false); }} className="text-neutral-400 hover:text-neutral-900 dark:hover:text-white cursor-pointer transition-colors">
                  <X size={13} />
                </button>
              </div>
            ) : (
              <button
                onClick={() => setIsSearching(true)}
                className="p-2.5 rounded-xl bg-neutral-100 dark:bg-neutral-800/80 hover:bg-neutral-200 dark:hover:bg-neutral-700 text-neutral-500 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-white transition-all cursor-pointer"
                title="Search messages"
              >
                <Search size={15} />
              </button>
            )}
          </div>
          <button
            onClick={handleClearChat}
            className="p-2.5 rounded-xl bg-neutral-100 dark:bg-neutral-800/80 hover:bg-red-50 dark:hover:bg-red-950/30 text-neutral-500 dark:text-neutral-400 hover:text-red-500 dark:hover:text-red-400 transition-all cursor-pointer"
            title="Clear chat"
          >
            <Trash size={15} />
          </button>
        </div>
      </div>

      {/* Messages Area */}
      <div
        ref={messagesContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-4 md:px-8 py-6 space-y-6"
        style={{
          backgroundImage: 'radial-gradient(circle at 20% 50%, rgba(var(--color-brand-rgb, 139,92,246), 0.03) 0%, transparent 50%), radial-gradient(circle at 80% 20%, rgba(var(--color-brand-rgb, 139,92,246), 0.02) 0%, transparent 50%)'
        }}
      >
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center space-y-4">
            <div className="w-16 h-16 rounded-2xl bg-brand/10 border border-brand/20 flex items-center justify-center text-brand">
              <MessageCircle size={26} />
            </div>
            <div className="max-w-xs">
              <h4 className="text-sm font-bold uppercase tracking-wider text-neutral-900 dark:text-white mb-1.5">No Messages Yet</h4>
              <p className="text-xs text-neutral-500 leading-relaxed">Channel initialized. Send your first message to begin the orchestration session.</p>
            </div>
          </div>
        ) : (
          Object.keys(groupedMessages).map((dateKey) => {
            const msgs = groupedMessages[dateKey];
            return (
              <div key={dateKey} className="space-y-4">

                {/* Date separator */}
                <div className="flex items-center justify-center gap-3 my-2">
                  <hr className="flex-1 border-t border-neutral-200 dark:border-neutral-800" />
                  <span className="px-3 py-1 text-[10px] uppercase tracking-widest font-bold text-neutral-400 dark:text-neutral-600 bg-neutral-100 dark:bg-neutral-900 rounded-full border border-neutral-200 dark:border-neutral-800">
                    {dateKey}
                  </span>
                  <hr className="flex-1 border-t border-neutral-200 dark:border-neutral-800" />
                </div>

                {msgs.map((msg, idx) => {
                  const isOwn = msg.senderId === currentUser?.uid;
                  const isEditing = editingMessageId === msg.id;

                  return (
                    <div
                      key={msg.id}
                      className={`flex items-end gap-3 group/msg msg-appear ${isOwn ? 'justify-end' : 'justify-start'}`}
                      style={{ animationDelay: `${idx * 30}ms` }}
                    >

                      {/* Other user avatar */}
                      {!isOwn && (
                        <div className="w-8 h-8 rounded-xl bg-neutral-200 dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-700 flex items-center justify-center text-neutral-600 dark:text-neutral-300 text-xs font-bold shrink-0 shadow-sm">
                          {msg.senderName.charAt(0).toUpperCase()}
                        </div>
                      )}

                      {/* Bubble */}
                      <div className={`max-w-[72%] space-y-1 ${isOwn ? 'items-end' : 'items-start'} flex flex-col`}>
                        {!isOwn && (
                          <span className="text-[10px] font-bold uppercase tracking-widest text-neutral-400 dark:text-neutral-500 px-1">
                            {msg.senderName}
                          </span>
                        )}

                        <div className={`relative px-4 py-3 text-sm rounded-2xl shadow-sm ${
                          isOwn
                            ? 'bg-gradient-to-br from-brand to-brand-hover text-white rounded-br-md shadow-brand/20'
                            : 'bg-light-surface dark:bg-dark-card border border-light-border dark:border-dark-border text-neutral-900 dark:text-neutral-100 rounded-bl-md'
                        }`}>
                          {isEditing ? (
                            <div className="flex flex-col gap-2 min-w-[220px]">
                              <textarea
                                value={editingMessageText}
                                onChange={(e) => setEditingMessageText(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleEditMessageSubmit(msg.id); }
                                  if (e.key === 'Escape') setEditingMessageId(null);
                                }}
                                className="w-full text-sm p-2.5 rounded-xl bg-light-surface dark:bg-dark-bg border border-brand text-neutral-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-brand/20 resize-none"
                                rows={2}
                              />
                              <div className="flex justify-end gap-1.5">
                                <button onClick={() => handleEditMessageSubmit(msg.id)} className="px-3 py-1.5 bg-green-500 text-white rounded-lg text-xs font-bold hover:bg-green-600 transition-colors cursor-pointer">Save</button>
                                <button onClick={() => setEditingMessageId(null)} className="px-3 py-1.5 bg-neutral-200 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-300 rounded-lg text-xs font-bold hover:bg-neutral-300 dark:hover:bg-neutral-600 transition-colors cursor-pointer">Cancel</button>
                              </div>
                            </div>
                          ) : (
                            <p className="whitespace-pre-wrap leading-relaxed break-words">{msg.text}</p>
                          )}

                          <div className={`flex items-center gap-1.5 mt-1.5 ${isOwn ? 'justify-end' : 'justify-start'}`}>
                            {msg.edited && <span className={`text-[9px] font-mono tracking-tighter ${isOwn ? 'text-white/60' : 'text-neutral-400'}`}>edited</span>}
                            <span className={`text-[9px] font-mono tracking-tighter ${isOwn ? 'text-white/60' : 'text-neutral-400 dark:text-neutral-500'}`}>
                              {format(msg.timestamp, 'HH:mm')}
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Own message actions — shown on hover */}
                      {isOwn && !isEditing && (
                        <div className="opacity-0 group-hover/msg:opacity-100 flex gap-1 self-end mb-6 transition-all duration-200">
                          <button
                            onClick={() => { setEditingMessageId(msg.id); setEditingMessageText(msg.text); }}
                            className="p-1.5 rounded-lg bg-light-surface dark:bg-dark-card border border-light-border dark:border-dark-border hover:border-brand hover:text-brand text-neutral-400 transition-colors cursor-pointer shadow-sm"
                          >
                            <Edit2 size={11} />
                          </button>
                          <button
                            onClick={() => handleDeleteMessage(msg.id)}
                            className="p-1.5 rounded-lg bg-light-surface dark:bg-dark-card border border-light-border dark:border-dark-border hover:border-red-400 hover:text-red-500 text-neutral-400 transition-colors cursor-pointer shadow-sm"
                          >
                            <Trash2 size={11} />
                          </button>
                        </div>
                      )}

                      {/* Own avatar */}
                      {isOwn && (
                        <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-brand to-brand-hover flex items-center justify-center text-white text-xs font-extrabold shrink-0 shadow-md shadow-brand/30">
                          {msg.senderName.charAt(0).toUpperCase()}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Scroll to bottom button */}
      {showScrollDown && (
        <button
          onClick={() => scrollToBottom('smooth')}
          className="absolute bottom-28 right-6 p-3 rounded-full bg-brand hover:bg-brand-hover text-white flex items-center justify-center z-10 cursor-pointer shadow-lg shadow-brand/40 transition-all hover:scale-110"
        >
          <ArrowDown size={15} />
        </button>
      )}

      {/* Message Input */}
      <div className="px-4 md:px-6 py-4 border-t border-light-border dark:border-dark-border bg-light-surface dark:bg-dark-surface shrink-0 transition-colors">
        {showEmojiPicker && (
          <div className="flex gap-1 p-2 bg-light-surface dark:bg-dark-card border border-light-border dark:border-dark-border rounded-2xl mb-3 w-fit shadow-xl backdrop-blur-sm">
            {QUICK_EMOJIS.map(emoji => (
              <button key={emoji} onClick={() => addEmoji(emoji)} className="hover:scale-125 transition-transform text-lg p-2 cursor-pointer rounded-xl hover:bg-neutral-100 dark:hover:bg-neutral-700">
                {emoji}
              </button>
            ))}
          </div>
        )}

        <form onSubmit={handleSendMessage} className="flex gap-2.5 items-center">
          <button
            type="button"
            onClick={() => setShowEmojiPicker(!showEmojiPicker)}
            className={`p-3 rounded-xl border transition-all shrink-0 cursor-pointer flex items-center justify-center ${
              showEmojiPicker
                ? 'bg-brand/10 border-brand text-brand'
                : 'bg-neutral-100 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400 border-neutral-200 dark:border-neutral-700 hover:bg-brand/10 hover:border-brand hover:text-brand dark:hover:text-brand'
            }`}
          >
            <Smile size={18} />
          </button>

          <div className="flex-1 relative">
            <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder="Ask the AMD Orchestration Engine..."
              className="w-full text-sm md:text-base px-5 py-3.5 rounded-2xl border border-light-border dark:border-dark-border bg-light-card dark:bg-dark-card text-neutral-900 dark:text-white placeholder:text-neutral-400 focus:outline-none focus:border-brand dark:focus:border-brand focus:bg-light-surface dark:focus:bg-dark-card focus:ring-2 focus:ring-brand/15 transition-all"
            />
          </div>

          <button
            type="submit"
            disabled={!inputText.trim()}
            className="p-3.5 rounded-xl bg-gradient-to-br from-brand to-brand-hover text-white shrink-0 hover:opacity-90 transition-all flex items-center justify-center cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed shadow-md shadow-brand/30 hover:shadow-lg hover:shadow-brand/40 hover:scale-105 disabled:shadow-none disabled:scale-100"
          >
            <Send size={17} />
          </button>
        </form>
      </div>
    </div>
  );
};
