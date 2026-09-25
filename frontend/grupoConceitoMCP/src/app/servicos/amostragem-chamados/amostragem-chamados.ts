const CASAS_DECIMAIS_MAXIMAS = 3;
const MILESIMOS_POR_UNIDADE = 1000;

/** Quantos de cada 10 chamados entram na amostra: `floor(10 × %)`, em inteiros (sem erro de float). */
export function analisadosPorDez(percentual: number): number {
  const milesimos = Math.round(percentual * MILESIMOS_POR_UNIDADE);
  return Math.floor((milesimos * 10) / (100 * MILESIMOS_POR_UNIDADE));
}

/** Percentual de 0 a 100 com até 3 casas (aceita vírgula), ou `null`; o backend valida de verdade. */
export function percentualValido(texto: string): number | null {
  const limpo = texto.trim().replace(',', '.');
  if (!/^\d+(\.\d+)?$/.test(limpo)) {
    return null;
  }

  const decimais = limpo.split('.')[1] ?? '';
  if (decimais.replace(/0+$/, '').length > CASAS_DECIMAIS_MAXIMAS) {
    return null;
  }

  const valor = Number(limpo);
  return valor >= 0 && valor <= 100 ? valor : null;
}
