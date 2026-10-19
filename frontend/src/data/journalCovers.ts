/** Publisher images are journal-specific. Unknown journals use a labelled placeholder,
 * never another journal's artwork. Cover choices can be overridden in the UI. */
const covers: Record<string, { image?: string; color: string; monogram: string; source?: string }> = {
  'nature communications': {
    image: 'https://media.springernature.com/lw630/nature-cms/uploads/cms/pages/2321/top_item_image/26-025263B_MWO_Option2-7bc07a49a787e7dc1a89f7ea9fbad649.jpg',
    color: '#17515a', monogram: 'NC', source: 'https://www.nature.com/ncomms/',
  },
  'nature': { image: 'https://media.springernature.com/w440/springer-static/cover-hires/journal/41586/658/8136', color: '#304333', monogram: 'N', source: 'https://www.nature.com/nature/' },
  'science': {
    image: 'https://www.science.org/cms/asset/c93716a1-3f86-4069-8791-dbc32abf16dd/science.2026.394.issue-6821.cover.gif',
    color: '#922929', monogram: 'S', source: 'https://www.science.org/journal/science',
  },
  'science advances': {
    image: 'https://www.science.org/cms/asset/697e0052-c330-4b71-90ec-51971ce0bb3c/sciadv.2026.12.issue-42.cover.gif',
    color: '#2b5690', monogram: 'SA', source: 'https://www.science.org/journal/sciadv',
  },
  'ieee transactions on pattern analysis and machine intelligence': { color: '#264862', monogram: 'TPAMI' },
  'journal of the american chemical society': { color: '#244f75', monogram: 'JACS' },
  'advanced materials': { color: '#785a40', monogram: 'AM' },
  'the lancet': { image: 'https://ars.els-cdn.com/content/image/X01406736.jpg', color: '#17445d', monogram: 'L', source: 'https://www.thelancet.com/journals/lancet/home' },
  'acm computing surveys': { color: '#2b6276', monogram: 'CSUR' },
  'ieee access': { color: '#23665c', monogram: 'IEEE' },
  'spe journal': { color: '#314967', monogram: 'SPE' },
  'marine and petroleum geology': { image: 'https://ars.els-cdn.com/content/image/X02648172.jpg', color: '#1f4750', monogram: 'MPG', source: 'https://www.sciencedirect.com/journal/marine-and-petroleum-geology' },
  'energy & fuels': { color: '#863e2c', monogram: 'E&F' },
}
export function journalCover(name: string) {
  return covers[name.trim().toLowerCase()] || { color: '#435269', monogram: name.split(' ').map(w => w[0]).join('').slice(0, 4).toUpperCase() }
}
