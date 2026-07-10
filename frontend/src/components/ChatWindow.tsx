import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { getFirebase } from '../firebase';
import { ref, push, set, remove, update, onValue } from 'firebase/database';
import { 
  Send, Trash2, Edit2, Check, X, 
  Smile, ShieldCheck, Sparkles, MessageCircle, 
  Search, Calendar, ArrowDown, Trash
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

const QUICK_EMOJIS = ['😀', '🔥', '👍', '❤️', '🎉', '💡', '🚀', '✨'];

export const ChatWindow: React.FC<ChatWindowProps> = ({ activeChatId }) => {
  const { currentUser, profileData } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState('');
  const [dbInstance, setDbInstance] = useState<any>(null);
  const [chatName, setChatName] = useState('Chat');

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
      if (data) { setChatName(data.name); setNewChatName(data.name); }
    });
    return () => unsubscribe();
  }, [dbInstance, activeChatId]);

  useEffect(() => {
    if (!dbInstance || !activeChatId) return;
    const messagesRef = ref(dbInstance, `messages/${activeChatId}`);
    const unsubscribe = onValue(messagesRef, (snapshot) => {
      const data = snapshot.val();
      if (data) {
        const list = Object.values(data) as Message[];
        list.sort((a, b) => a.timestamp - b.timestamp);
        setMessages(list);
      } else {
        setMessages([]);
      }
    });
    return () => unsubscribe();
  }, [dbInstance, activeChatId]);

  const scrollToBottom = (behavior: 'smooth' | 'auto' = 'smooth') => {
    messagesEndRef.current?.scrollIntoView({ behavior });
  };

  useEffect(() => { scrollToBottom('smooth'); }, [messages]);

  const handleScroll = () => {
    const container = messagesContainerRef.current;
    if (!container) return;
    const { scrollTop, scrollHeight, clientHeight } = container;
    setShowScrollDown(scrollHeight - scrollTop - clientHeight > 300);
  };

  const handleSendMessage = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!dbInstance || !currentUser || !profileData || !activeChatId || !inputText.trim()) return;
    const textToSend = inputText.trim();
    setInputText('');
    setShowEmojiPicker(false);
    try {
      const msgListRef = ref(dbInstance, `messages/${activeChatId}`);
      const newMsgRef = push(msgListRef);
      const newMsgId = newMsgRef.key;
      if (!newMsgId) return;
      const message: Message = {
        id: newMsgId, text: textToSend, senderId: currentUser.uid,
        senderName: profileData.displayName,
        senderAvatarColor: profileData.avatarColor || 'from-indigo-500 to-fuchsia-500',
        timestamp: Date.now(),
      };
      await set(newMsgRef, message);
      await update(ref(dbInstance, `chats/${activeChatId}`), { lastMessage: textToSend, lastMessageTime: Date.now() });
      scrollToBottom('smooth');
    } catch (err) { console.error(err); }
  };

  const handleRenameChat = async () => {
    if (!dbInstance || !activeChatId || !newChatName.trim()) return;
    try {
      await update(ref(dbInstance, `chats/${activeChatId}`), { name: newChatName.trim() });
      setIsRenamingChat(false);
    } catch (e) { console.error(e); }
  };

  const handleClearChat = async () => {
    if (!dbInstance || !activeChatId) return;
    if (confirm('Clear all messages in this conversation?')) {
      try {
        await remove(ref(dbInstance, `messages/${activeChatId}`));
        await update(ref(dbInstance, `chats/${activeChatId}`), { lastMessage: 'Messages cleared', lastMessageTime: Date.now() });
      } catch (e) { console.error(e); }
    }
  };

  const handleDeleteMessage = async (messageId: string) => {
    if (!dbInstance || !activeChatId) return;
    try {
      await remove(ref(dbInstance, `messages/${activeChatId}/${messageId}`));
      if (messages.length > 0 && messages[messages.length - 1].id === messageId) {
        const remaining = messages.filter(m => m.id !== messageId);
        const lastMsg = remaining.length > 0 ? remaining[remaining.length - 1].text : 'No messages';
        const lastMsgTime = remaining.length > 0 ? remaining[remaining.length - 1].timestamp : Date.now();
        await update(ref(dbInstance, `chats/${activeChatId}`), { lastMessage: lastMsg, lastMessageTime: lastMsgTime });
      }
    } catch (e) { console.error(e); }
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
      ? messages.filter(m => m.text.toLowerCase().includes(searchQuery.toLowerCase()))
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
      <div className="flex-1 h-full bg-slate-50 dark:bg-[#090a11] flex flex-col items-center justify-center p-8 text-center relative overflow-hidden">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-indigo-500/5 blur-3xl rounded-full pointer-events-none"></div>
        <div className="absolute top-1/3 left-1/3 w-[300px] h-[300px] bg-fuchsia-500/5 blur-3xl rounded-full pointer-events-none"></div>

        <div className="max-w-md space-y-6 relative z-10">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-3xl bg-indigo-500/10 border border-indigo-500/20 font-bold text-4xl shadow-xl shadow-black/10 mb-2 animate-float">
            ✨
          </div>
          <h2 className="text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white">
            Welcome to{' '}
            <span className="bg-gradient-to-r from-indigo-500 to-fuchsia-500 bg-clip-text text-transparent">
              AMDChat
            </span>
          </h2>
          <p className="text-slate-500 dark:text-slate-400 text-sm leading-relaxed">
            Create or select a conversation from the sidebar to start exchanging messages. Your conversations are updated in real-time and persisted using Firebase.
          </p>

          <div className="grid grid-cols-2 gap-4 mt-8 pt-6 border-t border-slate-200 dark:border-white/5">
            <div className="p-3 rounded-xl bg-white dark:bg-slate-900/35 border border-slate-200 dark:border-white/5 text-left shadow-sm">
              <span className="text-indigo-500 dark:text-indigo-400 flex items-center gap-1.5 text-xs font-semibold mb-1">
                <ShieldCheck size={14} /> Realtime Sync
              </span>
              <p className="text-[10px] text-slate-500">Instant database state reflection across all devices.</p>
            </div>
            <div className="p-3 rounded-xl bg-white dark:bg-slate-900/35 border border-slate-200 dark:border-white/5 text-left shadow-sm">
              <span className="text-fuchsia-500 dark:text-fuchsia-400 flex items-center gap-1.5 text-xs font-semibold mb-1">
                <Sparkles size={14} /> Micro-Aesthetics
              </span>
              <p className="text-[10px] text-slate-500">Premium design, gorgeous gradients, responsive layout.</p>
            </div>
          </div>

          <div className="mt-8 text-xs text-indigo-400/60 flex items-center justify-center gap-1">
            <MessageCircle size={14} /> Created with Tailwind CSS v4 & Firebase.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 h-full bg-slate-50 dark:bg-[#090a11] flex flex-col justify-between relative">

      {/* Chat Header */}
      <div className="h-16 border-b border-slate-200 dark:border-white/5 bg-white/90 dark:bg-[#0d0e17]/80 backdrop-blur-md px-6 flex items-center justify-between shrink-0 z-10">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-9 h-9 rounded-xl bg-indigo-50 dark:bg-indigo-500/10 border border-indigo-200 dark:border-indigo-500/20 text-indigo-500 dark:text-indigo-300 flex items-center justify-center text-sm font-semibold shrink-0">
            {chatName.charAt(0).toUpperCase()}
          </div>
          <div className="min-w-0">
            {isRenamingChat ? (
              <div className="flex items-center gap-1">
                <input
                  type="text" value={newChatName}
                  onChange={(e) => setNewChatName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleRenameChat(); if (e.key === 'Escape') setIsRenamingChat(false); }}
                  className="text-xs px-2.5 py-1 rounded bg-white dark:bg-slate-950 border border-indigo-400 dark:border-indigo-500/40 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-indigo-400"
                  autoFocus
                />
                <button onClick={handleRenameChat} className="text-emerald-500 p-1 hover:bg-slate-100 dark:hover:bg-white/5 rounded cursor-pointer"><Check size={14} /></button>
                <button onClick={() => setIsRenamingChat(false)} className="text-rose-400 p-1 hover:bg-slate-100 dark:hover:bg-white/5 rounded cursor-pointer"><X size={14} /></button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <h3
                  className="font-bold text-slate-800 dark:text-slate-100 truncate text-sm hover:text-indigo-500 dark:hover:text-indigo-300 cursor-pointer"
                  onClick={() => setIsRenamingChat(true)} title="Click to rename"
                >
                  {chatName}
                </h3>
                <button onClick={() => setIsRenamingChat(true)} className="text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 transition-colors p-0.5 cursor-pointer">
                  <Edit2 size={11} />
                </button>
              </div>
            )}
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
              <span className="text-[10px] text-slate-400 dark:text-slate-500">Active Realtime sync</span>
            </div>
          </div>
        </div>

        {/* Header Actions */}
        <div className="flex items-center gap-2">
          <div className="flex items-center">
            {isSearching ? (
              <div className="flex items-center gap-1.5 bg-white dark:bg-slate-950 border border-slate-200 dark:border-white/10 rounded-lg px-2.5 py-1 text-xs">
                <input
                  type="text" value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Filter messages..."
                  className="bg-transparent text-slate-700 dark:text-slate-200 focus:outline-none placeholder:text-slate-400 dark:placeholder:text-slate-600 w-32 md:w-48 text-[11px]"
                  autoFocus
                />
                <button onClick={() => { setSearchQuery(''); setIsSearching(false); }} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 cursor-pointer">
                  <X size={12} />
                </button>
              </div>
            ) : (
              <button
                onClick={() => setIsSearching(true)}
                className="p-2 rounded-xl bg-slate-100 dark:bg-white/5 hover:bg-slate-200 dark:hover:bg-white/10 border border-slate-200 dark:border-white/5 text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-all cursor-pointer"
              >
                <Search size={14} />
              </button>
            )}
          </div>
          <button
            onClick={handleClearChat}
            className="p-2 rounded-xl bg-slate-100 dark:bg-white/5 hover:bg-rose-50 dark:hover:bg-rose-500/10 border border-slate-200 dark:border-white/5 hover:border-rose-200 dark:hover:border-rose-500/25 text-slate-500 dark:text-slate-400 hover:text-rose-500 dark:hover:text-rose-400 transition-all cursor-pointer"
          >
            <Trash size={14} />
          </button>
        </div>
      </div>

      {/* Messages Area */}
      <div
        ref={messagesContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6"
      >
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center space-y-3 opacity-60">
            <div className="w-12 h-12 rounded-full bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-white/5 flex items-center justify-center text-xl">
              💬
            </div>
            <div className="max-w-xs">
              <h4 className="text-xs font-semibold text-slate-700 dark:text-slate-200">No Messages Yet</h4>
              <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-1">This is the start of your synchronized message log. Say hello to get started!</p>
            </div>
          </div>
        ) : (
          Object.entries(groupedMessages).map(([dateKey, msgs]) => (
            <div key={dateKey} className="space-y-4">

              {/* Date separator */}
              <div className="flex items-center justify-center gap-2">
                <hr className="flex-1 border-t border-slate-200 dark:border-white/5" />
                <span className="px-2.5 py-0.5 rounded-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-white/5 text-[9px] uppercase tracking-wider font-bold text-slate-400 dark:text-slate-500 flex items-center gap-1 shadow-sm">
                  <Calendar size={10} /> {dateKey}
                </span>
                <hr className="flex-1 border-t border-slate-200 dark:border-white/5" />
              </div>

              {msgs.map((msg) => {
                const isOwn = msg.senderId === currentUser?.uid;
                const isEditing = editingMessageId === msg.id;

                return (
                  <div key={msg.id} className={`flex items-start gap-2.5 group/msg ${isOwn ? 'justify-end' : 'justify-start'}`}>

                    {/* Other user avatar */}
                    {!isOwn && (
                      <div className={`w-8 h-8 rounded-xl bg-gradient-to-tr ${msg.senderAvatarColor || 'from-indigo-500 to-fuchsia-500'} flex items-center justify-center text-white text-[11px] font-bold shadow-sm shrink-0 mt-0.5`}>
                        {msg.senderName.charAt(0).toUpperCase()}
                      </div>
                    )}

                    {/* Bubble */}
                    <div className="max-w-[70%] space-y-1">
                      {!isOwn && (
                        <span className="text-[10px] font-semibold text-slate-500 dark:text-slate-400 px-1">
                          {msg.senderName}
                        </span>
                      )}

                      <div className={`relative rounded-2xl px-4 py-2.5 text-sm ${
                        isOwn
                          ? 'bg-gradient-to-tr from-indigo-600 to-indigo-500 text-white rounded-tr-none shadow-md shadow-indigo-600/10'
                          : 'bg-white dark:bg-[#121320] border border-slate-200 dark:border-white/5 text-slate-800 dark:text-slate-200 rounded-tl-none shadow-sm'
                      }`}>
                        {isEditing ? (
                          <div className="flex flex-col gap-2 min-w-[200px]">
                            <textarea
                              value={editingMessageText}
                              onChange={(e) => setEditingMessageText(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleEditMessageSubmit(msg.id); }
                                if (e.key === 'Escape') setEditingMessageId(null);
                              }}
                              className="w-full text-xs p-2 rounded bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-white/10 text-slate-900 dark:text-white focus:outline-none resize-none"
                              rows={2}
                            />
                            <div className="flex justify-end gap-1.5">
                              <button onClick={() => handleEditMessageSubmit(msg.id)} className="px-2 py-1 bg-emerald-50 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-500/20 hover:bg-emerald-100 dark:hover:bg-emerald-500/30 rounded text-[10px] font-semibold cursor-pointer">Save</button>
                              <button onClick={() => setEditingMessageId(null)} className="px-2 py-1 bg-slate-100 dark:bg-white/5 text-slate-500 dark:text-slate-400 border border-slate-200 dark:border-white/5 hover:bg-slate-200 dark:hover:bg-white/10 rounded text-[10px] font-semibold cursor-pointer">Cancel</button>
                            </div>
                          </div>
                        ) : (
                          <p className="whitespace-pre-wrap leading-relaxed break-words text-xs md:text-sm">{msg.text}</p>
                        )}

                        <div className="flex items-center justify-end gap-1 mt-1">
                          {msg.edited && <span className="text-[8px] opacity-40 uppercase tracking-widest font-bold">Edited</span>}
                          <span className={`text-[8px] ${isOwn ? 'text-indigo-200' : 'text-slate-400 dark:text-slate-500'}`}>
                            {format(msg.timestamp, 'h:mm a')}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Own message actions */}
                    {isOwn && !isEditing && (
                      <div className="opacity-0 group-hover/msg:opacity-100 flex flex-col md:flex-row gap-1 self-center transition-all">
                        <button
                          onClick={() => { setEditingMessageId(msg.id); setEditingMessageText(msg.text); }}
                          className="p-1 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-white/5 hover:text-indigo-500 dark:hover:text-indigo-400 text-slate-400 transition-colors cursor-pointer shadow-sm"
                        >
                          <Edit2 size={11} />
                        </button>
                        <button
                          onClick={() => handleDeleteMessage(msg.id)}
                          className="p-1 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-white/5 hover:text-rose-500 dark:hover:text-rose-400 text-slate-400 transition-colors cursor-pointer shadow-sm"
                        >
                          <Trash2 size={11} />
                        </button>
                      </div>
                    )}

                    {/* Own avatar */}
                    {isOwn && (
                      <div className={`w-8 h-8 rounded-xl bg-gradient-to-tr ${msg.senderAvatarColor || 'from-indigo-500 to-fuchsia-500'} flex items-center justify-center text-white text-[11px] font-bold shadow-sm shrink-0 mt-0.5`}>
                        {msg.senderName.charAt(0).toUpperCase()}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Scroll to bottom button */}
      {showScrollDown && (
        <button
          onClick={() => scrollToBottom('smooth')}
          className="absolute bottom-20 right-6 p-2 rounded-full bg-indigo-600 hover:bg-indigo-500 border border-indigo-500/20 text-white shadow-lg flex items-center justify-center animate-bounce z-10 cursor-pointer"
        >
          <ArrowDown size={14} />
        </button>
      )}

      {/* Message Input */}
      <div className="p-4 border-t border-slate-200 dark:border-white/5 bg-white/90 dark:bg-[#0a0b12]/80 backdrop-blur-md shrink-0">
        {showEmojiPicker && (
          <div className="flex gap-2 p-2 bg-white dark:bg-slate-950 border border-slate-200 dark:border-white/10 rounded-xl mb-2 w-fit shadow-md">
            {QUICK_EMOJIS.map(emoji => (
              <button key={emoji} onClick={() => addEmoji(emoji)} className="hover:scale-125 transition-transform text-md p-1 cursor-pointer">
                {emoji}
              </button>
            ))}
          </div>
        )}

        <form onSubmit={handleSendMessage} className="flex gap-2">
          <button
            type="button"
            onClick={() => setShowEmojiPicker(!showEmojiPicker)}
            className={`p-2.5 rounded-xl border transition-all shrink-0 cursor-pointer ${
              showEmojiPicker
                ? 'bg-indigo-50 dark:bg-indigo-500/20 text-indigo-500 dark:text-indigo-400 border-indigo-200 dark:border-indigo-500/30'
                : 'bg-slate-100 dark:bg-white/5 text-slate-500 dark:text-slate-400 border-slate-200 dark:border-white/5 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-200 dark:hover:bg-white/10'
            }`}
          >
            <Smile size={16} />
          </button>

          <input
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="Type your message here..."
            className="flex-1 text-xs md:text-sm px-4 rounded-xl border border-slate-200 dark:border-white/5 bg-slate-50 dark:bg-slate-950/40 text-slate-800 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-600 focus:outline-none focus:border-indigo-400 dark:focus:border-indigo-500/40 focus:ring-1 focus:ring-indigo-400/40 dark:focus:ring-indigo-500/40 transition-all"
          />

          <button
            type="submit"
            disabled={!inputText.trim()}
            className="p-2.5 rounded-xl bg-gradient-to-r from-indigo-500 to-indigo-600 disabled:from-slate-200 dark:disabled:from-slate-800 disabled:to-slate-200 dark:disabled:to-slate-800 text-white disabled:text-slate-400 dark:disabled:text-slate-600 shrink-0 hover:opacity-90 active:scale-[0.98] transition-all flex items-center justify-center cursor-pointer disabled:cursor-not-allowed shadow-md shadow-indigo-500/10"
          >
            <Send size={16} />
          </button>
        </form>
      </div>
    </div>
  );
};
