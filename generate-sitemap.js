// generate-sitemap.js
// Run: node generate-sitemap.js

const fs = require('fs');

const SITE_URL = 'https://roma.co.ke';

const content = JSON.parse(fs.readFileSync('data/content.json', 'utf8'));

const today = new Date().toISOString().split('T')[0];

let urls = `  <url>
    <loc>${SITE_URL}/</loc>
    <lastmod>${today}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>`;

content.forEach(item => {
  if (item.type === 'article') {
    const lastmod = item.date ? new Date(item.date).toISOString().split('T')[0] : today;
    urls += `
  <url>
    <loc>${SITE_URL}/?article=${item.id}</loc>
    <lastmod>${lastmod}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
  </url>`;
  }
});

const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls}
</urlset>`;

fs.writeFileSync('sitemap.xml', sitemap);
console.log(`✅ Sitemap generated with ${content.filter(i => i.type === 'article').length + 1} URLs`);