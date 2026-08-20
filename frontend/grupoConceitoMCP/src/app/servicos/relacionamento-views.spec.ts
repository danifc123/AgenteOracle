import { ViewFinanceira } from '../dadosRelatorios/views-financeiras';
import { construirGrafoRelacionamentos, tabelasAlcancaveis } from './relacionamento-views';

function view(nome: string, viewDestino?: string): ViewFinanceira {
  return {
    nome,
    descricao: '',
    colunas: [],
    relacionamentos: viewDestino
      ? [{ viewDestino, colunasLocais: ['x'], colunasDestino: ['y'], descricao: '' }]
      : [],
  };
}

describe('construirGrafoRelacionamentos', () => {
  it('conecta os dois lados do relacionamento, mesmo declarado só de um', () => {
    const grafo = construirGrafoRelacionamentos([view('a', 'b'), view('b')]);
    expect(grafo.get('a')).toEqual(new Set(['b']));
    expect(grafo.get('b')).toEqual(new Set(['a']));
  });

  it('view sem relacionamento nenhum fica isolada no grafo', () => {
    const grafo = construirGrafoRelacionamentos([view('a')]);
    expect(grafo.get('a')).toEqual(new Set());
  });
});

describe('tabelasAlcancaveis', () => {
  it('sem nada selecionado, devolve null (qualquer tabela pode ser a primeira)', () => {
    const grafo = construirGrafoRelacionamentos([view('a', 'b'), view('b')]);
    expect(tabelasAlcancaveis(grafo, [])).toBeNull();
  });

  it('alcança vizinho direto', () => {
    const grafo = construirGrafoRelacionamentos([view('a', 'b'), view('b')]);
    expect(tabelasAlcancaveis(grafo, ['a'])).toEqual(new Set(['a', 'b']));
  });

  it('alcança por caminho indireto (a-b-c)', () => {
    const grafo = construirGrafoRelacionamentos([view('a', 'b'), view('b', 'c'), view('c')]);
    expect(tabelasAlcancaveis(grafo, ['a'])).toEqual(new Set(['a', 'b', 'c']));
  });

  it('view sem relacionamento nenhum com a seleção não entra no resultado', () => {
    const grafo = construirGrafoRelacionamentos([view('a', 'b'), view('b'), view('isolada')]);
    expect(tabelasAlcancaveis(grafo, ['a'])).toEqual(new Set(['a', 'b']));
  });
});
