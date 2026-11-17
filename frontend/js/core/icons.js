/** Minimal line-icon set (24px grid, stroke = currentColor). icon('home') → <svg>. */
const PATHS = {
  home: 'M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z',
  history: 'M3 12a9 9 0 1 0 3-6.7M3 4v5h5M12 7v5l3 2',
  menu: 'M4 6h16M4 12h16M4 18h16',
  close: 'M6 6l12 12M18 6 6 18',
  logout: 'M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 17l5-5-5-5M15 12H3',
  inbox: 'M4 13h4l2 3h4l2-3h4M4 13l2.5-8h11L20 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z',
  search: 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-4-4',
  chevronLeft: 'M15 6l-6 6 6 6',
  chevronRight: 'M9 6l6 6-6 6',
  user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0',
  check: 'M5 12l5 5 9-10',
  shield: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z',
  layers: 'M12 3l9 5-9 5-9-5zM3 13l9 5 9-5',
  org: 'M9 3h6v4H9zM4 17h6v4H4zM14 17h6v4h-6zM12 7v5M7 17v-5h10v5',
  users: 'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21a7 7 0 0 1 14 0M16 3.5a4 4 0 0 1 0 7M22 21a7 7 0 0 0-4-6.3',
  plus: 'M12 5v14M5 12h14',
  edit: 'M4 20h4L19 9l-4-4L4 16zM14 6l4 4',
  trash: 'M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3',
  key: 'M14 10a4 4 0 1 0-1.2 2.8L20 20M17 17l2-2M15 15l1.5-1.5',
  chevronDown: 'M6 9l6 6 6-6',
  refresh: 'M20 11a8 8 0 0 0-14.9-3M4 4v4h4M4 13a8 8 0 0 0 14.9 3M20 20v-4h-4',
  list: 'M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01',
  form: 'M4 4h16v16H4zM8 9h8M8 13h8M8 17h5',
  type: 'M5 6V4h14v2M12 4v16M9 20h6',
  versions: 'M12 8v4l3 2M3 12a9 9 0 1 0 9-9M3 4v4h4',
  upload: 'M12 16V4M7 9l5-5 5 5M4 20h16',
  briefcase: 'M4 8h16v11H4zM9 8V5h6v3M4 13h16',
  calendar: 'M4 6h16v14H4zM4 10h16M8 3v4M16 3v4',
  target: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 12h.01',
  tasks: 'M10 6h10M10 12h10M10 18h10M4 6l1.5 1.5L8 5M4 12l1.5 1.5L8 11M4 18l1.5 1.5L8 17',
  chart: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
  grid: 'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
  flag: 'M5 21V4M5 4h11l-2 4 2 4H5',
  bell: 'M6 17V11a6 6 0 1 1 12 0v6l2 2H4zM10 21h4',
  branch: 'M6 3v12M6 15a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM18 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM18 9c0 6-12 3-12 6',
  copy: 'M8 8h12v12H8zM4 16V4h12',
  plug: 'M9 3v5M15 3v5M6 8h12v3a6 6 0 0 1-12 0zM12 17v4',
  route: 'M5 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM19 9a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM7 17h7a3 3 0 0 0 0-6h-4a3 3 0 0 1 0-6h7',
  sun: 'M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.8 1.2V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-2.8-1.2l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.7 1.7 0 0 0 3.2 15H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.2-2.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.7 1.7 0 0 0 9.9 4.2V4a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 2.8 1.2l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0 1.2 2.8H21a2 2 0 1 1 0 4h-.1z',
};

export function icon(name, { size = 18, label } = {}) {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', size);
  svg.setAttribute('height', size);
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.8');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  if (label) svg.setAttribute('aria-label', label);
  else svg.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS(ns, 'path');
  path.setAttribute('d', PATHS[name] || PATHS.layers);
  svg.append(path);
  return svg;
}
