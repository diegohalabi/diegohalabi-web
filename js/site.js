// Shared by index.html (English) and es/index.html (Spanish).
// The dark/light class is applied inline in <head> before paint (avoids a theme flash);
// publications and grants are pre-rendered by scripts/update_orcid.py.

const I18N = {
  en: {
    count: (n) => `${n} item${n !== 1 ? 's' : ''} found`,
    showMore: (n) => `Show More Publications (${n})`,
    empty: 'No publications found matching your criteria.',
  },
  es: {
    count: (n) => `${n} resultado${n !== 1 ? 's' : ''}`,
    showMore: (n) => `Ver más publicaciones (${n})`,
    empty: 'No hay publicaciones que coincidan con la búsqueda.',
  },
};
const t = I18N[document.documentElement.lang] || I18N.en;

// -------------------------------------------------------------
// 1. Theme toggle (persists and honors prefers-color-scheme)
// -------------------------------------------------------------
const themeToggleBtn = document.getElementById('theme-toggle');
const themeToggleDarkIcon = document.getElementById('theme-toggle-dark-icon');
const themeToggleLightIcon = document.getElementById('theme-toggle-light-icon');

function syncThemeIcons() {
  const isDark = document.documentElement.classList.contains('dark');
  themeToggleLightIcon.classList.toggle('hidden', !isDark);
  themeToggleDarkIcon.classList.toggle('hidden', isDark);
}
syncThemeIcons();

themeToggleBtn.addEventListener('click', () => {
  const isDark = document.documentElement.classList.toggle('dark');
  document.documentElement.classList.toggle('light', !isDark);
  try {
    localStorage.setItem('color-theme', isDark ? 'dark' : 'light');
  } catch (e) {
    // Storage unavailable (private mode, blocked cookies): the toggle still works for this visit
  }
  syncThemeIcons();
});

// -------------------------------------------------------------
// 2. Publication search, year filter & pagination
// -------------------------------------------------------------
const PAGE_SIZE = 5;
let showingAll = false;

const pubItems = Array.from(document.querySelectorAll('#publications-container [data-pub]'));
const countLabel = document.getElementById('pub-count');
const searchInput = document.getElementById('search-input');
const yearSelect = document.getElementById('year-select');
const showMoreBtn = document.getElementById('btn-show-more');
const paginationControls = document.getElementById('pagination-controls');
const emptyState = document.createElement('div');
emptyState.className = 'hidden p-8 text-center text-slate-500 text-sm';
emptyState.innerHTML = '<i class="fa-solid fa-folder-open text-slate-600 text-lg mb-2 block" aria-hidden="true"></i>';
emptyState.append(t.empty);
document.getElementById('publications-container').appendChild(emptyState);

// Case- and accent-insensitive matching ("halabi" finds "Halabí")
function normalize(text) {
  return text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
}

function populateYearsDropdown() {
  const years = [...new Set(pubItems.map(el => el.dataset.year))]
    .filter(y => y && y !== 'N/A')
    .sort((a, b) => parseInt(b) - parseInt(a));
  years.forEach(year => {
    const option = document.createElement('option');
    option.value = year;
    option.textContent = year;
    yearSelect.appendChild(option);
  });
}

function filterAndRender() {
  const query = normalize(searchInput.value);
  const year = yearSelect.value;
  const matches = pubItems.filter(el =>
    el.dataset.search.includes(query) && (year === 'all' || el.dataset.year === year)
  );

  pubItems.forEach(el => el.classList.add('hidden'));
  const visible = showingAll ? matches : matches.slice(0, PAGE_SIZE);
  visible.forEach(el => el.classList.remove('hidden'));

  countLabel.textContent = t.count(matches.length);
  emptyState.classList.toggle('hidden', matches.length > 0);

  const remaining = matches.length - visible.length;
  paginationControls.classList.toggle('hidden', remaining <= 0);
  if (remaining > 0) {
    showMoreBtn.innerHTML = `${t.showMore(remaining)} <i class="fa-solid fa-angle-down ml-1" aria-hidden="true"></i>`;
  }
}

searchInput.addEventListener('input', () => {
  showingAll = false;
  filterAndRender();
});

yearSelect.addEventListener('change', () => {
  showingAll = false;
  filterAndRender();
});

showMoreBtn.addEventListener('click', () => {
  showingAll = true;
  filterAndRender();
});

populateYearsDropdown();
filterAndRender();
