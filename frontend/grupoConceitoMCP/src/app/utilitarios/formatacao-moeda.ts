/** Formatação de valores em R$ para telas com números grandes (milhões/
 * bilhões) — em vez de "R$ 353.462.555,21" (cheio de zero, difícil de ler
 * rápido num card ou eixo de gráfico), mostra "R$ 353,5 Milhões". */

export interface ValorAbreviado {
  numero: string;
  unidade: string | null;
}

const UNIDADES = [
  { limite: 1_000_000_000, divisor: 1_000_000_000, nome: 'Bilhões' },
  { limite: 1_000_000, divisor: 1_000_000, nome: 'Milhões' },
  { limite: 1_000, divisor: 1_000, nome: 'Mil' },
] as const;

export function abreviarValor(valor: number): ValorAbreviado {
  const absoluto = Math.abs(valor);
  const unidade = UNIDADES.find((item) => absoluto >= item.limite);

  if (!unidade) {
    return { numero: valor.toLocaleString('pt-BR', { maximumFractionDigits: 0 }), unidade: null };
  }

  const numero = (valor / unidade.divisor).toLocaleString('pt-BR', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
  return { numero, unidade: unidade.nome };
}

export function formatarMoedaAbreviada(valor: number): string {
  const { numero, unidade } = abreviarValor(valor);
  return unidade ? `R$ ${numero} ${unidade}` : `R$ ${numero}`;
}
