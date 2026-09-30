import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { RespostaTetoTokensIa, TetoTokensIa } from './teto-tokens-ia';

const RESPOSTA_TI: RespostaTetoTokensIa = { dominio: 'ti', teto_tokens_diario: 50000, tokens_hoje: 1200 };
const RESPOSTA_RH: RespostaTetoTokensIa = { dominio: 'rh', teto_tokens_diario: 8000, tokens_hoje: 300 };

describe('TetoTokensIa', () => {
  let servico: TetoTokensIa;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    servico = TestBed.inject(TetoTokensIa);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('deveria carregar o teto e o consumo de hoje de um domínio', () => {
    servico.carregar('ti');

    const requisicao = http.expectOne((req) => req.url.endsWith('/api/ia/teto-tokens/ti'));
    requisicao.flush(RESPOSTA_TI);

    expect(requisicao.request.method).toBe('GET');
    expect(servico.teto()).toBe(50000);
    expect(servico.tokensHoje()).toBe(1200);
  });

  it('deveria carregar o domínio pedido, não um fixo', () => {
    servico.carregar('rh');

    const requisicao = http.expectOne((req) => req.url.endsWith('/api/ia/teto-tokens/rh'));
    requisicao.flush(RESPOSTA_RH);

    expect(servico.teto()).toBe(8000);
  });

  it('deveria enviar PUT com o novo teto e atualizar os signals com a resposta', () => {
    servico.salvar('ti', 99999).subscribe();

    const requisicao = http.expectOne((req) => req.url.endsWith('/api/ia/teto-tokens/ti'));
    requisicao.flush({ dominio: 'ti', teto_tokens_diario: 99999, tokens_hoje: 1200 });

    expect(requisicao.request.method).toBe('PUT');
    expect(requisicao.request.body).toEqual({ teto_tokens_diario: 99999 });
    expect(servico.teto()).toBe(99999);
  });

  it('deveria repassar o erro pra quem chamou quando o servidor recusa', () => {
    let erroRecebido: unknown;
    servico.salvar('ti', 1).subscribe({ error: (erro) => (erroRecebido = erro) });

    http
      .expectOne((req) => req.method === 'PUT')
      .flush({ erro: 'Só o administrador desse departamento...' }, { status: 403, statusText: 'Forbidden' });

    expect(erroRecebido).toBeTruthy();
  });
});
