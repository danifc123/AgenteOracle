import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { RelatoriosFixados } from './relatorios-fixados';

describe('RelatoriosFixados', () => {
  let servico: RelatoriosFixados;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    servico = TestBed.inject(RelatoriosFixados);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('carregar busca os fixados do módulo pedido com GET e atualiza o signal', () => {
    servico.carregar('financeiro:cadastros:fixados');

    const requisicao = http.expectOne((req) => req.url.endsWith('/api/relatorios-fixados/financeiro%3Acadastros%3Afixados'));
    expect(requisicao.request.method).toBe('GET');
    requisicao.flush({ nomes: ['FINR10', 'FINR20'] });

    expect(servico.nomes()).toEqual(['FINR10', 'FINR20']);
  });

  it('carregar com erro no backend esvazia o signal em vez de quebrar', () => {
    servico.carregar('financeiro:cadastros:fixados');

    const requisicao = http.expectOne((req) => req.method === 'GET');
    requisicao.flush('erro', { status: 500, statusText: 'Erro' });

    expect(servico.nomes()).toEqual([]);
  });

  it('salvar atualiza o signal otimisticamente antes da resposta do backend', () => {
    servico.salvar('financeiro:cadastros:fixados', ['FINR10']);

    expect(servico.nomes()).toEqual(['FINR10']);

    http.expectOne((req) => req.method === 'PUT').flush({ nomes: ['FINR10'] });
  });

  it('salvar chama PUT no módulo certo com o corpo certo', () => {
    servico.salvar('estoque:especifico-grupo-conceito:fixados', ['ROT1', 'ROT2']);

    const requisicao = http.expectOne(
      (req) => req.url.endsWith('/api/relatorios-fixados/estoque%3Aespecifico-grupo-conceito%3Afixados'),
    );
    expect(requisicao.request.method).toBe('PUT');
    expect(requisicao.request.body).toEqual({ nomes: ['ROT1', 'ROT2'] });
    requisicao.flush({ nomes: ['ROT1', 'ROT2'] });
  });

  it('salvar substitui o signal pelo que o backend devolveu de fato', () => {
    servico.salvar('financeiro:cadastros:fixados', ['FINR10']);

    http.expectOne((req) => req.method === 'PUT').flush({ nomes: ['FINR10', 'FINR20'] });

    expect(servico.nomes()).toEqual(['FINR10', 'FINR20']);
  });
});
