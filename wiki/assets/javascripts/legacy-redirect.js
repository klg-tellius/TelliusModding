(() => {
  const id = window.location.hash.replace(/^#\/?/, "") || "main";
  const route = window.TELLIUS_LEGACY_ROUTES?.[id] || "/";
  const repositoryBase = window.location.pathname.replace(/\/tellius_archive\.html$/, "");
  window.location.replace(`${repositoryBase}${route}`.replace(/\/+/g, "/"));
})();
