import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { getFirebase } from '../firebase';
import { ref, push, set, remove, update, onValue } from 'firebase/database';
import { 
  MessageSquare, Plus, Trash2, Edit2, Check, X, 
  Search, Edit3, CheckCircle2, Sun, Moon
} from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

interface Chat {
  id: string;
  name: string;
  createdBy: string;
  createdAt: number;
  lastMessage?: string;
  lastMessageTime?: number;
}

interface SidebarProps {
  activeChatId: string | null;
  setActiveChatId: (id: string | null) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ activeChatId, setActiveChatId }) => {
  const { currentUser, profileData, updateUserDisplayName } = useAuth();
  const { toggleTheme, isDark } = useTheme();
  const [chats, setChats] = useState<Chat[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [editingChatId, setEditingChatId] = useState<string | null>(null);
  const [editChatName, setEditChatName] = useState('');
  const [isEditingProfile, setIsEditingProfile] = useState(false);
  const [newDisplayName, setNewDisplayName] = useState(profileData?.displayName || '');
  const [dbInstance, setDbInstance] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    try {
      const { db } = getFirebase();
      setDbInstance(db);
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => {
    if (!dbInstance) return;

    const chatsRef = ref(dbInstance, 'chats');
    const unsubscribe = onValue(chatsRef, (snapshot) => {
      const data = snapshot.val();
      if (data) {
        const chatsList = Object.values(data) as Chat[];
        chatsList.sort((a, b) => {
          const timeA = a.lastMessageTime || a.createdAt;
          const timeB = b.lastMessageTime || b.createdAt;
          return timeB - timeA;
        });
        setChats(chatsList);
      } else {
        setChats([]);
      }
      setLoading(false);
    }, (error) => {
      console.error('Error fetching chats:', error);
      setLoading(false);
    });

    return () => unsubscribe();
  }, [dbInstance]);

  useEffect(() => {
    if (profileData) setNewDisplayName(profileData.displayName);
  }, [profileData]);

  const handleCreateChat = async () => {
    if (!dbInstance) return;
    try {
      const chatsRef = ref(dbInstance, 'chats');
      const newChatRef = push(chatsRef);
      const newChatId = newChatRef.key;
      if (!newChatId) return;

      const newChat: Chat = {
        id: newChatId,
        name: `Conversation #${chats.length + 1}`,
        createdBy: currentUser?.uid || 'anonymous',
        createdAt: Date.now(),
        lastMessage: 'Chat created. Start sending messages!',
        lastMessageTime: Date.now(),
      };

      await set(newChatRef, newChat);
      setActiveChatId(newChatId);
      setEditingChatId(newChatId);
      setEditChatName(newChat.name);
    } catch (e) {
      console.error('Error creating chat:', e);
    }
  };

  const handleRenameChat = async (chatId: string) => {
    if (!dbInstance || !editChatName.trim()) return;
    try {
      await update(ref(dbInstance, `chats/${chatId}`), { name: editChatName.trim() });
      setEditingChatId(null);
    } catch (e) {
      console.error('Error renaming chat:', e);
    }
  };

  const handleDeleteChat = async (chatId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!dbInstance) return;
    if (confirm('Delete this conversation and all its messages?')) {
      try {
        await remove(ref(dbInstance, `chats/${chatId}`));
        await remove(ref(dbInstance, `messages/${chatId}`));
        if (activeChatId === chatId) setActiveChatId(null);
      } catch (e) {
        console.error('Error deleting chat:', e);
      }
    }
  };

  const handleSaveProfile = async () => {
    if (!newDisplayName.trim()) return;
    try {
      await updateUserDisplayName(newDisplayName.trim());
      setIsEditingProfile(false);
    } catch (e) {
      console.error('Error saving profile:', e);
    }
  };

  const filteredChats = chats.filter(chat =>
    chat.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="w-80 h-full bg-white dark:bg-[#0c0d16] border-r border-slate-200 dark:border-white/5 flex flex-col shrink-0">

      {/* Header */}
      <div className="p-4 border-b border-slate-200 dark:border-white/5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <span className="w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/25 flex items-center justify-center text-sm">
              ✨
            </span>
            <span className="font-bold tracking-tight text-md bg-gradient-to-r from-indigo-500 to-fuchsia-500 bg-clip-text text-transparent">
              AMDChat
            </span>
          </div>

          <div className="flex items-center gap-1.5">
            <span className="px-2 py-0.5 rounded-full bg-indigo-500/10 border border-indigo-500/25 text-[10px] font-semibold text-indigo-500 dark:text-indigo-400">
              Realtime
            </span>
            {/* Theme Toggle */}
            <button
              onClick={toggleTheme}
              className="w-7 h-7 rounded-lg border border-slate-200 dark:border-white/10 bg-slate-100 dark:bg-slate-900/50 hover:bg-slate-200 dark:hover:bg-slate-800 flex items-center justify-center text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-all cursor-pointer"
              title={isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
            >
              {isDark ? <Sun size={13} /> : <Moon size={13} />}
            </button>
          </div>
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 dark:text-slate-500" size={14} />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search conversations..."
            className="w-full text-xs pl-9 pr-3 py-2 rounded-lg border border-slate-200 dark:border-white/5 bg-slate-50 dark:bg-slate-900/50 text-slate-700 dark:text-slate-200 placeholder:text-slate-400 dark:placeholder:text-slate-600 focus:outline-none focus:border-indigo-400 dark:focus:border-indigo-500/40 focus:ring-1 focus:ring-indigo-400/40 dark:focus:ring-indigo-500/40 transition-all"
          />
        </div>
      </div>

      {/* New Chat Button */}
      <div className="p-4 pb-2">
        <button
          onClick={handleCreateChat}
          className="w-full py-2.5 px-4 rounded-xl bg-gradient-to-r from-indigo-600/90 to-fuchsia-600/90 hover:from-indigo-600 hover:to-fuchsia-600 text-white font-medium text-xs flex items-center justify-center gap-2 hover:scale-[1.01] active:scale-[0.99] transition-all shadow-md shadow-indigo-500/10 cursor-pointer"
        >
          <Plus size={14} /> New Conversation
        </button>
      </div>

      {/* Chats List */}
      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-0.5">
        {loading ? (
          <div className="flex flex-col items-center justify-center h-32 space-y-2">
            <div className="w-5 h-5 rounded-full border-2 border-indigo-500/30 border-t-indigo-500 animate-spin"></div>
            <span className="text-[10px] text-slate-400 dark:text-slate-500">Loading chats...</span>
          </div>
        ) : filteredChats.length === 0 ? (
          <div className="text-center py-8 px-4">
            <MessageSquare className="mx-auto text-slate-300 dark:text-slate-600 mb-2" size={20} />
            <p className="text-xs text-slate-400 dark:text-slate-500">No conversations found</p>
          </div>
        ) : (
          filteredChats.map((chat) => {
            const isActive = activeChatId === chat.id;
            const isEditing = editingChatId === chat.id;

            return (
              <div
                key={chat.id}
                onClick={() => !isEditing && setActiveChatId(chat.id)}
                className={`group relative flex items-center gap-3 p-3 rounded-xl cursor-pointer transition-all border ${
                  isActive
                    ? 'bg-indigo-50 dark:bg-indigo-500/10 border-indigo-200 dark:border-indigo-500/20 text-indigo-900 dark:text-indigo-100'
                    : 'border-transparent text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5 hover:text-slate-900 dark:hover:text-slate-200'
                }`}
              >
                {/* Avatar */}
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 text-xs font-semibold ${
                  isActive
                    ? 'bg-indigo-100 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-500/30'
                    : 'bg-slate-100 dark:bg-slate-900 border border-slate-200 dark:border-white/5 text-slate-500 dark:text-slate-400'
                }`}>
                  {chat.name.charAt(0).toUpperCase()}
                </div>

                {/* Details */}
                <div className="flex-1 min-w-0 pr-6">
                  {isEditing ? (
                    <div className="flex items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="text"
                        value={editChatName}
                        onChange={(e) => setEditChatName(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleRenameChat(chat.id);
                          if (e.key === 'Escape') setEditingChatId(null);
                        }}
                        className="w-full text-xs px-2 py-0.5 rounded border border-indigo-400 dark:border-indigo-500/40 bg-white dark:bg-slate-950 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-indigo-400"
                        autoFocus
                      />
                      <button onClick={() => handleRenameChat(chat.id)} className="text-emerald-500 hover:text-emerald-600 p-0.5 rounded cursor-pointer">
                        <Check size={12} />
                      </button>
                      <button onClick={() => setEditingChatId(null)} className="text-rose-400 hover:text-rose-500 p-0.5 rounded cursor-pointer">
                        <X size={12} />
                      </button>
                    </div>
                  ) : (
                    <>
                      <div className="flex items-center justify-between mb-0.5">
                        <span className="font-semibold text-xs truncate block text-slate-800 dark:text-slate-200">
                          {chat.name}
                        </span>
                        {chat.lastMessageTime && (
                          <span className="text-[9px] text-slate-400 dark:text-slate-500 whitespace-nowrap">
                            {formatDistanceToNow(chat.lastMessageTime, { addSuffix: false })
                              .replace('about ', '').replace('less than a minute', 'now')
                              .replace(' minutes', 'm').replace(' minute', 'm')
                              .replace(' hours', 'h').replace(' hour', 'h')
                              .replace(' days', 'd').replace(' day', 'd')}
                          </span>
                        )}
                      </div>
                      <p className="text-[10px] text-slate-400 dark:text-slate-500 truncate">
                        {chat.lastMessage}
                      </p>
                    </>
                  )}
                </div>

                {/* Hover actions */}
                {!isEditing && (
                  <div className="absolute right-2 opacity-0 group-hover:opacity-100 flex items-center gap-1 transition-all">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditingChatId(chat.id);
                        setEditChatName(chat.name);
                      }}
                      className="p-1 rounded bg-white dark:bg-slate-950/80 hover:bg-slate-100 dark:hover:bg-slate-900 border border-slate-200 dark:border-white/5 hover:text-indigo-500 text-slate-400 transition-all cursor-pointer"
                    >
                      <Edit2 size={10} />
                    </button>
                    <button
                      onClick={(e) => handleDeleteChat(chat.id, e)}
                      className="p-1 rounded bg-white dark:bg-slate-950/80 hover:bg-slate-100 dark:hover:bg-slate-900 border border-slate-200 dark:border-white/5 hover:text-rose-500 text-slate-400 transition-all cursor-pointer"
                    >
                      <Trash2 size={10} />
                    </button>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* User Profile Footer */}
      <div className="p-4 border-t border-slate-200 dark:border-white/5 bg-slate-50 dark:bg-[#0a0b12]">
        {isEditingProfile ? (
          <div className="space-y-2">
            <label className="block text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">Edit Display Name</label>
            <div className="flex items-center gap-1.5">
              <input
                type="text"
                value={newDisplayName}
                onChange={(e) => setNewDisplayName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSaveProfile();
                  if (e.key === 'Escape') setIsEditingProfile(false);
                }}
                placeholder="Enter name..."
                className="flex-1 text-xs px-2.5 py-1.5 rounded-lg border border-slate-200 dark:border-white/10 bg-white dark:bg-slate-950 text-slate-900 dark:text-white placeholder:text-slate-400 dark:placeholder:text-slate-600 focus:outline-none focus:border-indigo-400 dark:focus:border-indigo-500/50"
                autoFocus
              />
              <button onClick={handleSaveProfile} className="p-1.5 rounded-lg bg-indigo-50 dark:bg-indigo-500/20 hover:bg-indigo-100 dark:hover:bg-indigo-500/30 text-indigo-500 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-500/20 cursor-pointer">
                <CheckCircle2 size={14} />
              </button>
              <button onClick={() => setIsEditingProfile(false)} className="p-1.5 rounded-lg bg-slate-100 dark:bg-white/5 hover:bg-slate-200 dark:hover:bg-white/10 text-slate-500 dark:text-slate-400 border border-slate-200 dark:border-white/5 cursor-pointer">
                <X size={14} />
              </button>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-2.5 min-w-0">
            {/* Avatar */}
            <div className={`w-9 h-9 rounded-xl bg-gradient-to-tr ${profileData?.avatarColor || 'from-indigo-500 to-fuchsia-500'} flex items-center justify-center text-white text-xs font-bold shadow-md shadow-black/10 relative shrink-0`}>
              {profileData?.displayName?.charAt(0).toUpperCase() || 'U'}
              <span className="absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full bg-emerald-500 border-2 border-white dark:border-[#0c0d16]"></span>
            </div>

            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1">
                <span className="font-semibold text-xs text-slate-800 dark:text-slate-200 truncate max-w-[120px] block">
                  {profileData?.displayName}
                </span>
                <button
                  onClick={() => {
                    setIsEditingProfile(true);
                    setNewDisplayName(profileData?.displayName || '');
                  }}
                  className="p-0.5 text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300 transition-colors cursor-pointer"
                  title="Edit Name"
                >
                  <Edit3 size={10} />
                </button>
              </div>
              <span className="text-[9px] text-slate-400 dark:text-slate-500 truncate block">
                Anonymous User
              </span>
            </div>
          </div>
        )}
      </div>

    </div>
  );
};
