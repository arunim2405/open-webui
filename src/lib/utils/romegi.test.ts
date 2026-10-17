import { describe, expect, it } from 'vitest';
import { isSimplifiedUser } from './romegi';

const on = { features: { romegi_simplified_ui: true } };
const off = { features: { romegi_simplified_ui: false } };

describe('isSimplifiedUser', () => {
	it('hides for regular user when flag on', () =>
		expect(isSimplifiedUser(on, { role: 'user' })).toBe(true));
	it('hides for pending user when flag on', () =>
		expect(isSimplifiedUser(on, { role: 'pending' })).toBe(true));
	it('never hides for admin', () => expect(isSimplifiedUser(on, { role: 'admin' })).toBe(false));
	it('does nothing when flag off', () =>
		expect(isSimplifiedUser(off, { role: 'user' })).toBe(false));
	it('does nothing when flag missing', () =>
		expect(isSimplifiedUser({}, { role: 'user' })).toBe(false));
	it('does nothing without config', () =>
		expect(isSimplifiedUser(undefined, { role: 'user' })).toBe(false));
	it('does nothing without user', () => expect(isSimplifiedUser(on, null)).toBe(false));
});
