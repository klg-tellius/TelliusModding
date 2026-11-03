(() => {
  const record = document.querySelector(".article-actions");
  if (!record) return;
  const repository = "https://github.com/klg-tellius/TelliusModding";
  const sourcePath = record.dataset.sourcePath;
  const title = record.dataset.articleTitle;
  record.querySelector(".source-link").href = `${repository}/blob/main/wiki/${sourcePath}`;
  record.querySelector(".history-link").href = `${repository}/commits/main/wiki/${sourcePath}`;
  const params = new URLSearchParams({
    template: "archive-correction.yml",
    title: `[Archive] ${title}`,
    article: title,
    url: window.location.href,
  });
  record.querySelector(".issue-link").href = `${repository}/issues/new?${params}`;
})();
