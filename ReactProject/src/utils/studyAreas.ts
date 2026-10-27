const names: Record<string, string> = { JJ: '金江', LC: '老城' };

export const studyAreaName = (code: string) => names[code] ?? code;
