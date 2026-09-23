import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { ProvedoresLlm } from './provedores';

const PROVEDOR_OLLAMA = {
  id: 1,
  nome: 'Ollama local',
  tipo_conexao: 'ollama',
  base_url: 'http://127.0.0.1:11434',
  api_key_configurada: false,
  projeto_id: '',
  modelo: 'qwen2.5-coder:7b',
  estilo_api: 'chat_completions',
  preco_entrada_por_1k: 0,
  preco_saida_por_1k: 0,
  moeda: 'R$',
  ativo: true,
  criado_em: '2026-09-23T00:00:00Z',
};

const PROVEDOR_OCI = {
  id: 2,
  nome: 'OCI Generative AI — gpt-oss-120b',
  tipo_conexao: 'openai_compativel',
  base_url: 'https://inference.generativeai.sa-saopaulo-1.oci.oraclecloud.com/openai/v1',
  api_key_configurada: true,
  projeto_id: 'ocid1.generativeaiproject.oc1...',
  modelo: 'openai.gpt-oss-120b',
  estilo_api: 'responses',
  preco_entrada_por_1k: 0.01,
  preco_saida_por_1k: 0.02,
  moeda: 'R$',
  ativo: false,
  criado_em: '2026-09-23T00:00:00Z',
};

function criar(provedoresIniciais: unknown[] = [PROVEDOR_OLLAMA, PROVEDOR_OCI]) {
  TestBed.configureTestingModule({
    imports: [ProvedoresLlm],
    providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
  });
  const fixture = TestBed.createComponent(ProvedoresLlm);
  const http = TestBed.inject(HttpTestingController);
  http.expectOne((req) => req.url.endsWith('/api/ti/provedores-llm') && req.method === 'GET').flush(provedoresIniciais);
  fixture.detectChanges();

  const el: HTMLElement = fixture.nativeElement;

  return {
    fixture,
    http,
    texto: () => el.textContent ?? '',
    linhas: () => Array.from(el.querySelectorAll('tbody tr')) as HTMLElement[],
    abrirCriar: () => {
      (Array.from(el.querySelectorAll('button')).find((b) => b.textContent?.includes('Novo provedor')) as HTMLButtonElement).click();
      fixture.detectChanges();
    },
    abrirEditar: (indice: number) => {
      const botoes = Array.from(el.querySelectorAll('tbody tr')[indice].querySelectorAll('button'));
      (botoes.find((b) => b.textContent?.includes('Editar')) as HTMLButtonElement).click();
      fixture.detectChanges();
    },
    clicarAtivar: (indice: number) => {
      const botoes = Array.from(el.querySelectorAll('tbody tr')[indice].querySelectorAll('button'));
      (botoes.find((b) => b.textContent?.includes('Ativar')) as HTMLButtonElement).click();
      fixture.detectChanges();
    },
    clicarApagar: (indice: number) => {
      const botoes = Array.from(el.querySelectorAll('tbody tr')[indice].querySelectorAll('button'));
      (botoes.find((b) => b.textContent?.includes('Apagar')) as HTMLButtonElement).click();
      fixture.detectChanges();
    },
    confirmarApagar: () => {
      const botoes = Array.from(el.querySelectorAll('app-confirmacao-dialog button')) as HTMLButtonElement[];
      (botoes.find((b) => b.textContent?.includes('Apagar')) as HTMLButtonElement).click();
      fixture.detectChanges();
    },
    botaoDialogPrincipal: () =>
      Array.from(el.querySelectorAll('app-dialog .rodape-form button')).find(
        (b) => b.textContent?.includes('Criar provedor') || b.textContent?.includes('Salvar alterações'),
      ) as HTMLButtonElement,
  };
}

describe('ProvedoresLlm', () => {
  afterEach(() => {
    TestBed.inject(HttpTestingController).verify();
  });

  it('carrega e mostra a lista de provedores cadastrados', () => {
    const { texto } = criar();

    expect(texto()).toContain('Ollama local');
    expect(texto()).toContain('OCI Generative AI — gpt-oss-120b');
  });

  it('sem nenhum provedor cadastrado, mostra a mensagem de lista vazia', () => {
    const { texto } = criar([]);

    expect(texto()).toContain('Nenhum provedor cadastrado');
  });

  it('mostra o status ativo/inativo e a chave configurada/sem chave', () => {
    const { linhas } = criar();

    expect(linhas()[0].textContent).toContain('Ativo');
    expect(linhas()[0].textContent).toContain('Sem chave');
    expect(linhas()[1].textContent).toContain('Inativo');
    expect(linhas()[1].textContent).toContain('Configurada');
  });

  it('só o provedor inativo mostra o botão "Ativar"', () => {
    const { linhas } = criar();

    expect(Array.from(linhas()[0].querySelectorAll('button')).some((b) => b.textContent?.includes('Ativar'))).toBe(
      false,
    );
    expect(Array.from(linhas()[1].querySelectorAll('button')).some((b) => b.textContent?.includes('Ativar'))).toBe(
      true,
    );
  });

  it('ativar um provedor chama a rota certa e atualiza a lista com a resposta', () => {
    const { fixture, clicarAtivar, http, linhas } = criar();

    clicarAtivar(1);

    const requisicao = http.expectOne(
      (req) => req.url.endsWith('/api/ti/provedores-llm/2/ativar') && req.method === 'POST',
    );
    requisicao.flush([
      { ...PROVEDOR_OLLAMA, ativo: false },
      { ...PROVEDOR_OCI, ativo: true },
    ]);
    fixture.detectChanges();

    expect(linhas()[1].textContent).toContain('Ativo');
  });

  it('apagar pede confirmação antes de chamar o backend', () => {
    const { clicarApagar, texto, http } = criar();

    clicarApagar(0);

    expect(texto()).toContain('Apagar o provedor "Ollama local"?');
    http.expectNone((req) => req.method === 'DELETE');
  });

  it('apagar o provedor ativo avisa que o sistema volta pro Ollama padrão', () => {
    const { clicarApagar, texto } = criar();

    clicarApagar(0); // PROVEDOR_OLLAMA está ativo

    expect(texto()).toContain('sistema volta a usar o Ollama padrão do .env');
  });

  it('confirmar apagar chama DELETE e remove da lista', () => {
    const { fixture, clicarApagar, confirmarApagar, http, linhas } = criar();

    clicarApagar(0);
    confirmarApagar();

    http.expectOne((req) => req.url.endsWith('/api/ti/provedores-llm/1') && req.method === 'DELETE').flush({});
    fixture.detectChanges();

    expect(linhas().length).toBe(1);
    expect(linhas()[0].textContent).toContain('OCI Generative AI');
  });

  it('abrir o diálogo de criação começa com os campos vazios', () => {
    const { abrirCriar, texto } = criar();

    abrirCriar();

    expect(texto()).toContain('Novo provedor');
  });

  it('criar sem preencher nome/endereço/modelo mostra erro e não chama o backend', () => {
    const { fixture, abrirCriar, botaoDialogPrincipal, texto, http } = criar();

    abrirCriar();
    botaoDialogPrincipal().click();
    fixture.detectChanges();

    expect(texto()).toContain('Preencha nome, endereço e modelo.');
    http.expectNone((req) => req.method === 'POST');
  });

  it('editar pré-preenche o formulário com os dados do provedor', () => {
    const { abrirEditar, texto } = criar();

    abrirEditar(1);

    expect(texto()).toContain('Editar "OCI Generative AI — gpt-oss-120b"');
    expect(texto()).toContain('Deixe em branco pra manter a chave atual.');
  });
});
