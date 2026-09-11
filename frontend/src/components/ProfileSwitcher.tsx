import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown, Plus, Check, Trash2, Users } from 'lucide-react';

export interface Profile {
  id: string;
  name: string;
  relation: string;
  dob?: string | null;
  birth_time?: string | null;
  birth_place?: string | null;
  gender?: string | null;
  language?: string;
  isPrimary?: boolean;
}

interface ProfileSwitcherProps {
  profiles: Profile[];
  activeProfileId: string;
  onSelectProfile: (id: string) => void;
  onAddProfileClick: () => void;
  onEditProfile?: (profile: Profile) => void;
  onDeleteProfile?: (id: string) => void;
}

const RELATION_ICONS: Record<string, string> = {
  Self: '✨',
  Partner: '❤️',
  Mother: '🌸',
  Father: '🌟',
  Child: '👶',
  Friend: '🤝',
  Other: '👤',
};

export const ProfileSwitcher: React.FC<ProfileSwitcherProps> = ({
  profiles,
  activeProfileId,
  onSelectProfile,
  onAddProfileClick,
  onEditProfile,
  onDeleteProfile,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const activeProfile = profiles.find((p) => p.id === activeProfileId) || profiles[0];

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const getRelationEmoji = (relation?: string) => {
    return RELATION_ICONS[relation || 'Self'] || '👤';
  };

  return (
    <div className="relative inline-block text-left" ref={dropdownRef}>
      {/* Active Profile Pill Button */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 bg-slate-100 hover:bg-slate-200 text-slate-800 px-3 py-1.5 rounded-full text-xs font-semibold border border-slate-200/80 transition-all shadow-sm active:scale-95"
        title="Switch Profile"
      >
        <span className="flex items-center justify-center w-5 h-5 rounded-full bg-white text-[11px] shadow-xs">
          {getRelationEmoji(activeProfile?.relation)}
        </span>
        <span className="max-w-[110px] truncate font-medium">
          {activeProfile?.name || 'My Profile'}
        </span>
        <span className="text-[10px] uppercase font-bold text-slate-400 bg-white/80 px-1.5 py-0.5 rounded-md">
          {activeProfile?.relation || 'Self'}
        </span>
        <ChevronDown size={14} className={`text-slate-400 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute left-0 sm:right-0 sm:left-auto mt-2 w-76 bg-white rounded-2xl shadow-xl border border-slate-200/90 py-2 z-50 animate-in fade-in slide-in-from-top-2 duration-150">
          <div className="px-3.5 py-2 border-b border-slate-100 flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 uppercase tracking-wider">
              <Users size={13} />
              <span>Saved Charts ({profiles.length})</span>
            </div>
            <span className="text-[10px] text-slate-400 font-medium">Click to switch</span>
          </div>

          {/* Profile List */}
          <div className="max-h-64 overflow-y-auto py-1 divide-y divide-slate-50">
            {profiles.map((profile) => {
              const isSelected = profile.id === activeProfileId;
              return (
                <div
                  key={profile.id}
                  className={`flex items-center justify-between px-3.5 py-2.5 hover:bg-slate-50 transition-colors cursor-pointer group ${
                    isSelected ? 'bg-amber-50/70' : ''
                  }`}
                  onClick={() => {
                    onSelectProfile(profile.id);
                    setIsOpen(false);
                  }}
                >
                  <div className="flex items-center gap-2.5 min-w-0 flex-1">
                    <div className="w-7 h-7 rounded-full bg-slate-100 flex items-center justify-center text-sm shrink-0 border border-slate-200">
                      {getRelationEmoji(profile.relation)}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs font-semibold text-slate-800 truncate">
                          {profile.name || 'Unnamed'}
                        </span>
                        {profile.isPrimary && (
                          <span className="text-[9px] bg-amber-100 text-amber-700 font-semibold px-1 rounded shrink-0">
                            Primary
                          </span>
                        )}
                      </div>
                      <div className="text-[10px] text-slate-400 truncate">
                        {profile.relation || 'Self'} {profile.dob ? `• ${profile.dob}` : ''}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-1 shrink-0 ml-2">
                    {isSelected && (
                      <span className="p-1 text-amber-600 bg-amber-100 rounded-full mr-1">
                        <Check size={12} />
                      </span>
                    )}

                    {onEditProfile && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setIsOpen(false);
                          onEditProfile(profile);
                        }}
                        className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                        title="Edit Details & Relation"
                      >
                        <span className="text-xs">✏️</span>
                      </button>
                    )}

                    {!profile.isPrimary && onDeleteProfile && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (confirm(`Delete chart profile for ${profile.name || 'this person'}?`)) {
                            onDeleteProfile(profile.id);
                          }
                        }}
                        className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                        title="Delete Profile"
                      >
                        <Trash2 size={13} />
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Add Profile Action */}
          <div className="pt-2 px-2 border-t border-slate-100 mt-1">
            <button
              type="button"
              onClick={() => {
                setIsOpen(false);
                onAddProfileClick();
              }}
              className="w-full flex items-center justify-center gap-2 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 py-2 rounded-xl transition-all active:scale-[0.98]"
            >
              <Plus size={14} />
              <span>Add New Profile (Family / Partner)</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProfileSwitcher;
