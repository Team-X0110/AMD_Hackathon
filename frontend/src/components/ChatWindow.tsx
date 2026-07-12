import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../context/AuthContext';
import { getFirebase } from '../firebase';
import { ref, push, set, remove, update, onValue } from 'firebase/database';
import { 
  Send, Trash2, Edit2, Check, X, 
  Smile, ShieldCheck, Sparkles, MessageCircle, 
  Search, Calendar, ArrowDown, Trash, Terminal
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
        const msgs = Object.values(data) as Message[];
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
      <div className="flex-1 h-full bg-white dark:bg-[#0a0a0a] flex flex-col items-center justify-center p-8 text-center relative overflow-hidden">
        <div className="max-w-lg space-y-6 relative z-10 w-full">
          <div className="w-full border border-neutral-200 dark:border-neutral-900 bg-neutral-50 dark:bg-[#111111] p-10 rounded-sm shadow-sm flex flex-col items-center">
            <Terminal size={32} className="text-neutral-300 dark:text-neutral-700 mb-4" />
            <h2 className="text-xl font-bold tracking-tight text-neutral-900 dark:text-white uppercase mb-2">
              System Standby
            </h2>
            <p className="text-neutral-500 dark:text-neutral-400 text-sm leading-relaxed mb-8 max-w-md mx-auto">
              No active session selected. Initiate a new session from the sidebar or resume an existing one to begin localized LLM execution.
            </p>
            
            <div className="w-full flex justify-between items-center text-[10px] font-mono text-neutral-400 dark:text-neutral-600 border-t border-neutral-200 dark:border-neutral-800 pt-4 mt-2 uppercase">
              <span>Status: Awaiting Input</span>
              <span>Sync: Established</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 h-full bg-white dark:bg-[#0a0a0a] flex flex-col justify-between relative">

      {/* Chat Header */}
      <div className="h-16 border-b border-neutral-200 dark:border-neutral-900 bg-white dark:bg-[#111111] px-6 flex items-center justify-between shrink-0 z-10">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 rounded-sm bg-neutral-100 dark:bg-[#181818] border border-neutral-200 dark:border-neutral-800 text-neutral-600 dark:text-neutral-400 flex items-center justify-center text-sm font-bold shrink-0">
            {chatName.charAt(0).toUpperCase()}
          </div>
          <div className="min-w-0">
            {isRenamingChat ? (
              <div className="flex items-center gap-1.5">
                <input
                  type="text" value={newChatName}
                  onChange={(e) => setNewChatName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleRenameChat(); if (e.key === 'Escape') setIsRenamingChat(false); }}
                  className="text-xs px-2.5 py-1 rounded-sm bg-white dark:bg-[#181818] border border-[#ED1C24] text-neutral-900 dark:text-white focus:outline-none"
                  autoFocus
                />
                <button onClick={handleRenameChat} className="text-green-600 hover:text-green-700 p-1 cursor-pointer"><Check size={14} /></button>
                <button onClick={() => setIsRenamingChat(false)} className="text-red-500 hover:text-red-600 p-1 cursor-pointer"><X size={14} /></button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <h3
                  className="font-bold text-neutral-900 dark:text-white truncate text-sm hover:text-[#ED1C24] dark:hover:text-[#ED1C24] cursor-pointer transition-colors"
                  onClick={() => { setIsRenamingChat(true); setNewChatName(chatName); }} title="Rename Session"
                >
                  {chatName}
                </h3>
                <button onClick={() => { setIsRenamingChat(true); setNewChatName(chatName); }} className="text-neutral-400 hover:text-neutral-900 dark:hover:text-white transition-colors p-0.5 cursor-pointer">
                  <Edit2 size={12} />
                </button>
              </div>
            )}
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className="w-1.5 h-1.5 rounded-full bg-[#ED1C24]"></span>
              <span className="text-[10px] text-neutral-500 font-mono tracking-tighter uppercase">Sync Active</span>
            </div>
          </div>
        </div>

        {/* Header Actions */}
        <div className="flex items-center gap-2">
          <div className="flex items-center">
            {isSearching ? (
              <div className="flex items-center gap-1.5 bg-white dark:bg-[#181818] border border-neutral-300 dark:border-neutral-800 rounded-sm px-2.5 py-1 text-xs">
                <input
                  type="text" value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Filter..."
                  className="bg-transparent text-neutral-900 dark:text-white focus:outline-none placeholder:text-neutral-500 w-24 md:w-40 text-xs"
                  autoFocus
                />
                <button onClick={() => { setSearchQuery(''); setIsSearching(false); }} className="text-neutral-400 hover:text-neutral-900 dark:hover:text-white cursor-pointer">
                  <X size={12} />
                </button>
              </div>
            ) : (
              <button
                onClick={() => setIsSearching(true)}
                className="p-2 rounded-sm bg-neutral-100 dark:bg-[#181818] hover:bg-neutral-200 dark:hover:bg-neutral-800 border border-neutral-200 dark:border-neutral-800 text-neutral-500 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-white transition-colors cursor-pointer"
              >
                <Search size={14} />
              </button>
            )}
          </div>
          <button
            onClick={handleClearChat}
            className="p-2 rounded-sm bg-neutral-100 dark:bg-[#181818] hover:bg-red-50 dark:hover:bg-red-950/30 border border-neutral-200 dark:border-neutral-800 hover:border-red-200 dark:hover:border-red-900/50 text-neutral-500 dark:text-neutral-400 hover:text-red-600 dark:hover:text-red-400 transition-colors cursor-pointer"
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
            <div className="w-12 h-12 border-2 border-neutral-200 dark:border-neutral-800 flex items-center justify-center text-neutral-400 dark:text-neutral-600">
              <MessageCircle size={20} />
            </div>
            <div className="max-w-xs">
              <h4 className="text-xs font-bold uppercase tracking-wider text-neutral-900 dark:text-white">Empty Log</h4>
              <p className="text-[10px] text-neutral-500 mt-1">Data transmission channel established. Awaiting input.</p>
            </div>
          </div>
        ) : (
          Object.entries(groupedMessages).map(([dateKey, msgs]) => (
            <div key={dateKey} className="space-y-4">

              {/* Date separator */}
              <div className="flex items-center justify-center gap-4">
                <hr className="flex-1 border-t border-neutral-200 dark:border-neutral-800" />
                <span className="px-2 py-0.5 text-[9px] uppercase tracking-widest font-bold text-neutral-400 dark:text-neutral-600 flex items-center gap-1.5">
                   {dateKey}
                </span>
                <hr className="flex-1 border-t border-neutral-200 dark:border-neutral-800" />
              </div>

              {msgs.map((msg) => {
                const isOwn = msg.senderId === currentUser?.uid;
                const isEditing = editingMessageId === msg.id;

                return (
                  <div key={msg.id} className={`flex items-start gap-3 group/msg ${isOwn ? 'justify-end' : 'justify-start'}`}>

                    {/* Other user avatar */}
                    {!isOwn && (
                      <div className="w-8 h-8 rounded-sm bg-neutral-200 dark:bg-[#181818] border border-neutral-300 dark:border-neutral-800 flex items-center justify-center text-neutral-600 dark:text-neutral-400 text-[11px] font-bold shrink-0">
                        {msg.senderName.charAt(0).toUpperCase()}
                      </div>
                    )}

                    {/* Bubble */}
                    <div className="max-w-[75%] space-y-1">
                      {!isOwn && (
                        <span className="text-[10px] font-bold uppercase tracking-wider text-neutral-500 dark:text-neutral-500">
                          {msg.senderName}
                        </span>
                      )}

                      <div className={`relative px-4 py-3 text-sm rounded-sm ${
                        isOwn
                          ? 'bg-[#181818] dark:bg-[#181818] text-white border border-neutral-800'
                          : 'bg-white dark:bg-[#111111] border border-neutral-200 dark:border-neutral-800 text-neutral-900 dark:text-neutral-200'
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
                              className="w-full text-xs p-2 rounded-sm bg-white dark:bg-[#0a0a0a] border border-[#ED1C24] text-neutral-900 dark:text-white focus:outline-none resize-none"
                              rows={2}
                            />
                            <div className="flex justify-end gap-1.5">
                              <button onClick={() => handleEditMessageSubmit(msg.id)} className="px-3 py-1 bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-500 border border-green-200 dark:border-green-900/50 hover:bg-green-100 dark:hover:bg-green-900/40 rounded-sm text-[10px] font-bold uppercase cursor-pointer">Commit</button>
                              <button onClick={() => setEditingMessageId(null)} className="px-3 py-1 bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400 border border-neutral-200 dark:border-neutral-700 hover:bg-neutral-200 dark:hover:bg-neutral-700 rounded-sm text-[10px] font-bold uppercase cursor-pointer">Abort</button>
                            </div>
                          </div>
                        ) : (
                          <p className="whitespace-pre-wrap leading-relaxed break-words text-xs md:text-sm font-sans">{msg.text}</p>
                        )}

                        <div className="flex items-center justify-end gap-2 mt-2">
                          {msg.edited && <span className="text-[9px] text-neutral-400 dark:text-neutral-600 font-mono tracking-tighter">EDITED</span>}
                          <span className="text-[9px] text-neutral-400 dark:text-neutral-600 font-mono tracking-tighter">
                            {format(msg.timestamp, 'HH:mm:ss')}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Own message actions */}
                    {isOwn && !isEditing && (
                      <div className="opacity-0 group-hover/msg:opacity-100 flex flex-col md:flex-row gap-1 self-start transition-opacity mt-1">
                        <button
                          onClick={() => { setEditingMessageId(msg.id); setEditingMessageText(msg.text); }}
                          className="p-1.5 rounded-sm bg-neutral-100 dark:bg-[#181818] border border-neutral-200 dark:border-neutral-800 hover:text-neutral-900 dark:hover:text-white text-neutral-500 transition-colors cursor-pointer"
                        >
                          <Edit2 size={12} />
                        </button>
                        <button
                          onClick={() => handleDeleteMessage(msg.id)}
                          className="p-1.5 rounded-sm bg-neutral-100 dark:bg-[#181818] border border-neutral-200 dark:border-neutral-800 hover:text-[#ED1C24] dark:hover:text-[#ED1C24] text-neutral-500 transition-colors cursor-pointer"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    )}

                    {/* Own avatar */}
                    {isOwn && (
                      <div className="w-8 h-8 rounded-sm bg-[#ED1C24] flex items-center justify-center text-white text-[11px] font-bold shrink-0">
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
          className="absolute bottom-20 right-6 p-2 rounded-sm bg-[#ED1C24] hover:bg-[#c9171e] text-white flex items-center justify-center z-10 cursor-pointer shadow-sm transition-colors"
        >
          <ArrowDown size={14} />
        </button>
      )}

      {/* Message Input */}
      <div className="p-4 border-t border-neutral-200 dark:border-neutral-900 bg-white dark:bg-[#111111] shrink-0">
        {showEmojiPicker && (
          <div className="flex gap-1 p-2 bg-white dark:bg-[#181818] border border-neutral-200 dark:border-neutral-800 rounded-sm mb-2 w-fit shadow-sm">
            {QUICK_EMOJIS.map(emoji => (
              <button key={emoji} onClick={() => addEmoji(emoji)} className="hover:scale-110 transition-transform text-sm p-1.5 cursor-pointer rounded-sm hover:bg-neutral-100 dark:hover:bg-neutral-800">
                {emoji}
              </button>
            ))}
          </div>
        )}

        <form onSubmit={handleSendMessage} className="flex gap-2">
          <button
            type="button"
            onClick={() => setShowEmojiPicker(!showEmojiPicker)}
            className={`p-3 rounded-sm border transition-colors shrink-0 cursor-pointer flex items-center justify-center ${
              showEmojiPicker
                ? 'bg-neutral-200 dark:bg-neutral-800 text-neutral-900 dark:text-white border-neutral-300 dark:border-neutral-700'
                : 'bg-neutral-100 dark:bg-[#181818] text-neutral-500 dark:text-neutral-400 border-neutral-200 dark:border-neutral-800 hover:text-neutral-900 dark:hover:text-white'
            }`}
          >
            <Smile size={16} />
          </button>

          <input
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="Transmit data..."
            className="flex-1 text-sm px-4 py-3 rounded-sm border border-neutral-300 dark:border-neutral-800 bg-white dark:bg-[#0a0a0a] text-neutral-900 dark:text-white placeholder:text-neutral-500 focus:outline-none focus:border-[#ED1C24] dark:focus:border-[#ED1C24] transition-colors"
          />

          <button
            type="submit"
            disabled={!inputText.trim()}
            className="px-5 rounded-sm bg-[#ED1C24] disabled:bg-neutral-200 dark:disabled:bg-neutral-800 text-white disabled:text-neutral-400 dark:disabled:text-neutral-600 shrink-0 hover:bg-[#c9171e] transition-colors flex items-center justify-center cursor-pointer disabled:cursor-not-allowed uppercase font-bold text-[11px] tracking-wider"
          >
            Transmit
          </button>
        </form>
      </div>
    </div>
  );
};
