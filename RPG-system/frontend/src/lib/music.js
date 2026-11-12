export function musicEmbed(url, autoplay = true) {
  if (!url) return '';
  const youtube = url.match(/(?:youtube\.com\/(?:watch\?v=|embed\/)|youtu\.be\/)([\w-]+)/i);
  if (youtube) return `https://www.youtube.com/embed/${youtube[1]}?autoplay=${autoplay ? 1 : 0}&controls=1`;
  const spotify = url.match(/open\.spotify\.com\/(track|album|playlist)\/([\w-]+)/i);
  return spotify ? `https://open.spotify.com/embed/${spotify[1]}/${spotify[2]}` : '';
}
