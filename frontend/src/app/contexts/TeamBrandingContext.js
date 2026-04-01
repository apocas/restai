import { createContext, useContext, useMemo, useState, useCallback } from "react";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";

const TeamBrandingContext = createContext({
  branding: null,
  teamName: null,
  activeTeamId: null,
  brandedTeams: [],
  setActiveTeamId: () => {},
});

function findBrandedTeam(teams, preferredId) {
  if (!teams || teams.length === 0) return null;

  // If user has a preference, use it
  if (preferredId) {
    const preferred = teams.find((t) => t.id === preferredId);
    if (preferred) return preferred;
  }

  // Fall back to first team that has branding configured
  const withBranding = teams.find(
    (t) => t.branding && (t.branding.primary_color || t.branding.secondary_color || t.branding.logo_url || t.branding.app_name)
  );
  if (withBranding) return withBranding;

  // No team has branding
  return null;
}

export function TeamBrandingProvider({ children }) {
  const { user, isAuthenticated } = useAuth();
  const [overrideTeamId, setOverrideTeamId] = useState(null);

  const setActiveTeamId = useCallback((teamId) => {
    setOverrideTeamId(teamId);
    // Persist preference to backend
    if (user && user.token) {
      api.patch("/users/" + user.username, { options: { preferred_team_id: teamId } }, user.token).catch(() => {});
    }
  }, [user]);

  const value = useMemo(() => {
    if (!isAuthenticated || !user) {
      return { branding: null, teamName: null, activeTeamId: null, brandedTeams: [], setActiveTeamId };
    }

    const allTeams = [...(user.teams || []), ...(user.admin_teams || [])];
    // Deduplicate by id
    const seen = new Set();
    const uniqueTeams = allTeams.filter((t) => {
      if (seen.has(t.id)) return false;
      seen.add(t.id);
      return true;
    });

    // Teams that have any branding configured
    const brandedTeams = uniqueTeams.filter(
      (t) => t.branding && (t.branding.primary_color || t.branding.secondary_color || t.branding.logo_url || t.branding.app_name)
    );

    const preferredId = overrideTeamId || user.options?.preferred_team_id;
    const activeTeam = findBrandedTeam(uniqueTeams, preferredId);

    const branding = activeTeam?.branding || null;
    const hasAny = branding && (branding.primary_color || branding.secondary_color || branding.logo_url || branding.app_name || branding.welcome_message);

    return {
      branding: hasAny ? branding : null,
      teamName: activeTeam?.name || null,
      activeTeamId: activeTeam?.id || null,
      brandedTeams,
      setActiveTeamId,
    };
  }, [isAuthenticated, user, overrideTeamId, setActiveTeamId]);

  return (
    <TeamBrandingContext.Provider value={value}>
      {children}
    </TeamBrandingContext.Provider>
  );
}

export function useTeamBranding() {
  return useContext(TeamBrandingContext);
}
