const fs = require("fs");

const html = fs.readFileSync("docs/tellius_archive.html", "utf8");
const marker = '<script>\n"use strict"';
const start = html.indexOf(marker);
const end = html.lastIndexOf("</script>");
if (start < 0 || end < 0) throw new Error("archive script not found");
const script = html.slice(start + "<script>".length, end);
new Function(script);
console.log("OK: JavaScript syntax");
