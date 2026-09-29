import { TestBed } from '@angular/core/testing';
import { DownloadArquivo, extrairNomeArquivo } from './download-arquivo';
import { Toasts } from '../toasts/toasts';

describe('extrairNomeArquivo', () => {
  it('extrai o nome do header Content-Disposition', () => {
    expect(extrairNomeArquivo('attachment; filename="relatorio.xlsx"', 'padrao.xlsx')).toBe('relatorio.xlsx');
  });

  it('sem header, usa o nome padrão', () => {
    expect(extrairNomeArquivo(null, 'padrao.xlsx')).toBe('padrao.xlsx');
  });

  it('header sem filename, usa o nome padrão', () => {
    expect(extrairNomeArquivo('attachment', 'padrao.xlsx')).toBe('padrao.xlsx');
  });
});

describe('DownloadArquivo', () => {
  let servico: DownloadArquivo;
  let toasts: Toasts;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    servico = TestBed.inject(DownloadArquivo);
    toasts = TestBed.inject(Toasts);
  });

  it('baixar dispara o aviso da Área de Trabalho', () => {
    const blob = new Blob(['conteudo'], { type: 'text/plain' });

    servico.baixar(blob, 'arquivo.xlsx');

    const itens = toasts.itens();
    expect(itens.length).toBe(1);
    expect(itens[0].tipo).toBe('aviso');
    expect(itens[0].mensagem).toContain('Área de Trabalho');
  });
});
