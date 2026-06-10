import { useEffect, useMemo, useState } from "react";

export const PAGE_SIZE = 10;

/**
 * Client-side pagination for list UIs.
 * @param {Array} items - Full list to paginate
 * @param {{ pageSize?: number, resetKey?: unknown }} [options]
 */
export function usePagination(items, { pageSize = PAGE_SIZE, resetKey } = {}) {
  const [page, setPage] = useState(1);

  useEffect(() => {
    setPage(1);
  }, [resetKey]);

  const totalItems = items.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize) || 1);

  useEffect(() => {
    setPage((current) => Math.min(current, totalPages));
  }, [totalPages]);

  const paginatedItems = useMemo(() => {
    const start = (page - 1) * pageSize;
    return items.slice(start, start + pageSize);
  }, [items, page, pageSize]);

  return {
    page,
    setPage,
    pageSize,
    totalItems,
    totalPages,
    paginatedItems,
    hasPrev: page > 1,
    hasNext: page < totalPages,
  };
}
