/**
 * Format the two persisted satellite alias fields as one user-facing value.
 * The fields have different data sources, so this intentionally does not
 * merge or modify them in storage.
 */
export const formatAlternativeSatelliteNames = (alternativeName, nameOther) => {
    const seen = new Set();

    return [alternativeName, nameOther]
        .map((name) => String(name || '').trim())
        .filter((name) => {
            const normalizedName = name.toLocaleLowerCase();
            if (!normalizedName || seen.has(normalizedName)) {
                return false;
            }
            seen.add(normalizedName);
            return true;
        })
        .join(', ');
};
