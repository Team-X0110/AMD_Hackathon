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
        name: `Session ${chats.length + 1}`,
        createdBy: currentUser?.uid || 'anonymous',
        createdAt: Date.now(),
        lastMessage: 'Session initialized.',
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
    if (confirm('Terminate session and flush data?')) {
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
    <div className="w-72 md:w-80 h-full bg-neutral-50 dark:bg-[#111111] border-r border-neutral-200 dark:border-neutral-900 flex flex-col shrink-0 font-sans transition-colors">

      {/* Header */}
      <div className="px-5 pt-5 pb-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 bg-[#ED1C24] flex items-center justify-center font-bold text-white text-[10px]">A</div>
            <span className="font-bold tracking-tight text-neutral-900 dark:text-white uppercase">
              AMDChat
            </span>
          </div>

          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 rounded-sm bg-neutral-200 dark:bg-neutral-800 text-[10px] font-bold text-neutral-600 dark:text-neutral-400 uppercase tracking-wider">
              Local
            </span>
            {/* Theme Toggle */}
            <button
              onClick={toggleTheme}
              className="p-1.5 rounded-sm hover:bg-neutral-200 dark:hover:bg-neutral-800 text-neutral-500 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-white transition-colors cursor-pointer"
              title={isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
            >
              {isDark ? <Sun size={14} /> : <Moon size={14} />}
            </button>
          </div>
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" size={14} />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search sessions..."
            className="w-full text-xs pl-9 pr-3 py-2 rounded-sm border border-neutral-300 dark:border-neutral-800 bg-white dark:bg-[#181818] text-neutral-900 dark:text-neutral-200 placeholder:text-neutral-400 dark:placeholder:text-neutral-600 focus:outline-none focus:border-[#ED1C24] dark:focus:border-[#ED1C24] transition-colors"
          />
        </div>
      </div>

      {/* New Chat Button */}
      <div className="px-4 pb-2">
        <button
          onClick={handleCreateChat}
          className="w-full py-2 px-4 rounded-sm bg-white dark:bg-[#181818] border border-neutral-300 dark:border-neutral-800 hover:border-[#ED1C24] dark:hover:border-[#ED1C24] text-neutral-900 dark:text-white font-medium text-xs flex items-center justify-between transition-colors cursor-pointer"
        >
          <span>New Session</span>
          <Plus size={14} className="text-[#ED1C24]" />
        </button>
      </div>

      {/* Chats List */}
      <div className="flex-1 overflow-y-auto pt-2 space-y-0.5 px-2">
        {loading ? (
          <div className="flex flex-col items-center justify-center h-32 space-y-3">
            <div className="w-4 h-4 rounded-sm border-2 border-neutral-300 dark:border-neutral-700 border-t-[#ED1C24] animate-spin"></div>
            <span className="text-[10px] text-neutral-500 uppercase tracking-widest">Loading...</span>
          </div>
        ) : filteredChats.length === 0 ? (
          <div className="text-center py-8 px-4">
            <MessageSquare className="mx-auto text-neutral-300 dark:text-neutral-700 mb-2" size={20} />
            <p className="text-xs text-neutral-500">No active sessions</p>
          </div>
        ) : (
          filteredChats.map((chat) => {
            const isActive = activeChatId === chat.id;
            const isEditing = editingChatId === chat.id;

            return (
              <div
                key={chat.id}
                onClick={() => !isEditing && setActiveChatId(chat.id)}
                className={`group relative flex items-center gap-3 p-2.5 cursor-pointer transition-colors ${
                  isActive
                    ? 'bg-neutral-200/50 dark:bg-[#181818] border-l-2 border-[#ED1C24] text-neutral-900 dark:text-white'
                    : 'border-l-2 border-transparent text-neutral-600 dark:text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-900/50'
                }`}
              >
                {/* Avatar / Initial */}
                <div className={`w-7 h-7 rounded-sm flex items-center justify-center shrink-0 text-xs font-bold ${
                  isActive
                    ? 'bg-[#ED1C24] text-white'
                    : 'bg-neutral-200 dark:bg-neutral-800 text-neutral-500'
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
                        className="w-full text-xs px-2 py-0.5 rounded-sm border border-[#ED1C24] bg-white dark:bg-[#111111] text-neutral-900 dark:text-white focus:outline-none"
                        autoFocus
                      />
                      <button onClick={() => handleRenameChat(chat.id)} className="text-green-600 hover:text-green-700 p-0.5 cursor-pointer">
                        <Check size={12} />
                      </button>
                      <button onClick={() => setEditingChatId(null)} className="text-red-500 hover:text-red-600 p-0.5 cursor-pointer">
                        <X size={12} />
                      </button>
                    </div>
                  ) : (
                    <>
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-medium text-xs truncate block text-neutral-800 dark:text-neutral-200">
                          {chat.name}
                        </span>
                        {chat.lastMessageTime && (
                          <span className="text-[9px] text-neutral-400 dark:text-neutral-500 font-mono tracking-tighter">
                            {formatDistanceToNow(chat.lastMessageTime, { addSuffix: false })
                              .replace('about ', '').replace('less than a minute', 'now')
                              .replace(' minutes', 'm').replace(' minute', 'm')
                              .replace(' hours', 'h').replace(' hour', 'h')
                              .replace(' days', 'd').replace(' day', 'd')}
                          </span>
                        )}
                      </div>
                      <p className="text-[10px] text-neutral-500 dark:text-neutral-600 truncate">
                        {chat.lastMessage}
                      </p>
                    </>
                  )}
                </div>

                {/* Hover actions */}
                {!isEditing && (
                  <div className="absolute right-2 opacity-0 group-hover:opacity-100 flex items-center gap-0.5 transition-opacity">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditingChatId(chat.id);
                        setEditChatName(chat.name);
                      }}
                      className="p-1.5 rounded-sm bg-white dark:bg-neutral-800 hover:bg-neutral-100 dark:hover:bg-neutral-700 text-neutral-400 hover:text-neutral-900 dark:hover:text-white transition-colors cursor-pointer"
                    >
                      <Edit2 size={12} />
                    </button>
                    <button
                      onClick={(e) => handleDeleteChat(chat.id, e)}
                      className="p-1.5 rounded-sm bg-white dark:bg-neutral-800 hover:bg-red-50 dark:hover:bg-red-950/30 text-neutral-400 hover:text-red-600 dark:hover:text-red-400 transition-colors cursor-pointer"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* User Profile Footer */}
      <div className="p-4 border-t border-neutral-200 dark:border-neutral-900 bg-white dark:bg-[#181818]">
        {isEditingProfile ? (
          <div className="space-y-2">
            <label className="block text-[10px] font-bold uppercase tracking-widest text-neutral-500">Identity Alias</label>
            <div className="flex items-center gap-1.5">
              <input
                type="text"
                value={newDisplayName}
                onChange={(e) => setNewDisplayName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSaveProfile();
                  if (e.key === 'Escape') setIsEditingProfile(false);
                }}
                placeholder="Alias..."
                className="flex-1 text-xs px-2 py-1.5 rounded-sm border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-[#111111] text-neutral-900 dark:text-white focus:outline-none focus:border-[#ED1C24]"
                autoFocus
              />
              <button onClick={handleSaveProfile} className="p-1.5 rounded-sm bg-green-50 dark:bg-green-900/20 text-green-600 dark:text-green-500 hover:bg-green-100 dark:hover:bg-green-900/40 cursor-pointer transition-colors">
                <CheckCircle2 size={14} />
              </button>
              <button onClick={() => setIsEditingProfile(false)} className="p-1.5 rounded-sm bg-neutral-100 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400 hover:bg-neutral-200 dark:hover:bg-neutral-700 cursor-pointer transition-colors">
                <X size={14} />
              </button>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-3 min-w-0">
            {/* Avatar */}
            <div className="w-8 h-8 rounded-sm bg-neutral-200 dark:bg-neutral-800 flex items-center justify-center text-neutral-600 dark:text-neutral-300 text-xs font-bold relative shrink-0">
              {profileData?.displayName?.charAt(0).toUpperCase() || 'U'}
              <span className="absolute -bottom-1 -right-1 w-2.5 h-2.5 bg-green-500 border-2 border-white dark:border-[#181818] rounded-full"></span>
            </div>

            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <span className="font-semibold text-xs text-neutral-900 dark:text-white truncate block">
                  {profileData?.displayName}
                </span>
                <button
                  onClick={() => {
                    setIsEditingProfile(true);
                    setNewDisplayName(profileData?.displayName || '');
                  }}
                  className="p-0.5 text-neutral-400 hover:text-neutral-900 dark:hover:text-white transition-colors cursor-pointer"
                  title="Configure Alias"
                >
                  <Edit3 size={12} />
                </button>
              </div>
              <span className="text-[9px] font-mono text-neutral-500 dark:text-neutral-600 truncate block">
                ID: {currentUser?.uid?.substring(0, 8) || 'GUEST'}
              </span>
            </div>
          </div>
        )}
      </div>

    </div>
  );
};
