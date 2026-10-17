// RomeGI: whether power-user features are hidden for this user.
// Admins always see everything; the flag only affects other roles.
export const isSimplifiedUser = (
	config: { features?: { romegi_simplified_ui?: boolean } } | null | undefined,
	user: { role?: string } | null | undefined
): boolean => config?.features?.romegi_simplified_ui === true && !!user && user.role !== 'admin';
