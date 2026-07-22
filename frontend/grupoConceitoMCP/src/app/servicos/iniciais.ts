/** Iniciais pra avatar sem foto: primeira letra do primeiro nome + primeira
 * letra do segundo nome (ex: "João Silva" -> "JS"). Com um nome só, usa as
 * duas primeiras letras dele. */
export function iniciais(nome: string): string {
  const partes = nome.trim().split(/\s+/).filter(Boolean);

  if (!partes.length) {
    return '';
  }

  if (partes.length === 1) {
    return partes[0].slice(0, 2).toUpperCase();
  }

  return (partes[0][0] + partes[1][0]).toUpperCase();
}
