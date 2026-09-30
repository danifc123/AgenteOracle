import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { Sessao } from '../../../../servicos/sessao/sessao';
import { RespostaTetoTokensIa, TetoTokensIa } from '../../../../servicos/teto-tokens-ia/teto-tokens-ia';
import {
  ChamadosIaResposta,
  LinhaUsoIa,
  LinhaUsoIaPorDia,
  LinhaUsoIaPorUsuario,
  UsoIa,
} from '../../../../servicos/uso-ia/uso-ia';
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
  capacidades: ['chat'],
  credenciais_configuradas: false,
  // Sem chave nenhuma configurada (`api_key_configurada`/
  // `credenciais_configuradas` os dois `false`) — a idade da credencial
  // nem chega a aparecer pra esse provedor, então o valor aqui não importa.
  credencial_atualizada_em: '2026-09-23T00:00:00Z',
  ativo: true,
  ativo_embedding: false,
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
  capacidades: ['chat'],
  credenciais_configuradas: false,
  // Dinâmico (não fixo) de propósito: este provedor TEM chave configurada
  // (`api_key_configurada: true`), então a idade dela aparece na tela —
  // fixo, esse valor viraria "credencial velha" sozinho com o tempo e
  // quebraria testes que não são sobre idade de credencial.
  credencial_atualizada_em: new Date().toISOString(),
  ativo: false,
  ativo_embedding: false,
  criado_em: '2026-09-23T00:00:00Z',
};

const CHAMADOS_IA_VAZIO: ChamadosIaResposta = {
  total_chamados: 0,
  avaliados_insuficientes: 0,
  com_fallback_embedding: 0,
  duracao_media_ms: 0,
};

function tetoTokensIaFalso(
  salvar = vi.fn(() => of<RespostaTetoTokensIa>({ dominio: 'ti', teto_tokens_diario: 5000, tokens_hoje: 0 })),
) {
  return {
    teto: signal<number | null>(1000),
    tokensHoje: signal(0),
    carregar: vi.fn(),
    salvar,
  };
}

function usoIaFalso(opcoes: {
  consumo?: LinhaUsoIa[];
  tokensHojePorDominio?: Record<string, number>;
  porUsuario?: LinhaUsoIaPorUsuario[];
  porDia?: LinhaUsoIaPorDia[];
} = {}) {
  return {
    consumo: signal(opcoes.consumo ?? []),
    porUsuario: signal(opcoes.porUsuario ?? []),
    porDia: signal(opcoes.porDia ?? []),
    tokensHojePorDominio: signal(opcoes.tokensHojePorDominio ?? {}),
    chamadosIa: signal<ChamadosIaResposta | null>(CHAMADOS_IA_VAZIO),
    carregar: vi.fn(),
  };
}

// A tela inteira era só-desenvolvedor até 2026-09-28 (agora o time de TI
// também acessa, em modo leitura — ver `TestSomenteLeituraParaTime` mais
// abaixo) — os testes existentes assumem acesso de escrita, então o padrão
// aqui é `true`; sem essa fake, o `Sessao` real injetado (sem sessão
// nenhuma) devolveria `false` e esconderia botão nenhum dos testes acham.
function sessaoFalso(ehDesenvolvedor = true, ehAdminDoModulo = false) {
  return { ehDesenvolvedor: () => ehDesenvolvedor, ehAdminDoModulo: () => ehAdminDoModulo };
}

function criar(
  provedoresIniciais: unknown[] = [PROVEDOR_OLLAMA, PROVEDOR_OCI],
  tetoTokensIa = tetoTokensIaFalso(),
  usoIa = usoIaFalso(),
  sessao = sessaoFalso(),
) {
  TestBed.configureTestingModule({
    imports: [ProvedoresLlm],
    providers: [
      provideRouter([]),
      provideHttpClient(),
      provideHttpClientTesting(),
      { provide: TetoTokensIa, useValue: tetoTokensIa },
      { provide: UsoIa, useValue: usoIa },
      { provide: Sessao, useValue: sessao },
    ],
  });
  const fixture = TestBed.createComponent(ProvedoresLlm);
  const http = TestBed.inject(HttpTestingController);
  http.expectOne((req) => req.url.endsWith('/api/ti/provedores-llm') && req.method === 'GET').flush(provedoresIniciais);
  // A tabela começa fechada por padrão (ver `TestTabelaColapsavel` mais
  // abaixo, que testa esse padrão especificamente) — os outros testes
  // deste arquivo assumem a lista já visível, então abre aqui.
  fixture.componentInstance.tabelaProvedoresAberta.set(true);
  fixture.detectChanges();

  const el: HTMLElement = fixture.nativeElement;

  return {
    fixture,
    http,
    el,
    tetoTokensIa,
    usoIa,
    texto: () => el.textContent ?? '',
    linhasProvedores: () => Array.from(el.querySelectorAll('.tabela-provedores tbody tr')) as HTMLElement[],
    linhasConsumo: () => Array.from(el.querySelectorAll('.tabela-consumo tbody tr')) as HTMLElement[],
    abrirCriar: () => {
      (Array.from(el.querySelectorAll('button')).find((b) => b.textContent?.includes('Novo provedor')) as HTMLButtonElement).click();
      fixture.detectChanges();
    },
    // As ações (Ativar/Desativar/Editar/Apagar) ficam dentro do menu
    // suspenso do `app-menu-acoes` — abre o gatilho da linha antes de
    // procurar o botão, igual um usuário de verdade precisaria clicar.
    abrirMenuAcoes: (indice: number) => {
      (el.querySelectorAll('.tabela-provedores tbody tr')[indice].querySelector('.gatilho') as HTMLButtonElement).click();
      fixture.detectChanges();
    },
    abrirEditar: (indice: number) => {
      (el.querySelectorAll('.tabela-provedores tbody tr')[indice].querySelector('.gatilho') as HTMLButtonElement).click();
      fixture.detectChanges();
      const botoes = Array.from(el.querySelectorAll('.tabela-provedores tbody tr')[indice].querySelectorAll('button'));
      (botoes.find((b) => b.textContent?.includes('Editar')) as HTMLButtonElement).click();
      fixture.detectChanges();
    },
    clicarAtivar: (indice: number) => {
      (el.querySelectorAll('.tabela-provedores tbody tr')[indice].querySelector('.gatilho') as HTMLButtonElement).click();
      fixture.detectChanges();
      const botoes = Array.from(el.querySelectorAll('.tabela-provedores tbody tr')[indice].querySelectorAll('button'));
      (botoes.find((b) => b.textContent?.trim() === 'Ativar (chat)') as HTMLButtonElement).click();
      fixture.detectChanges();
    },
    clicarAtivarEmbedding: (indice: number) => {
      (el.querySelectorAll('.tabela-provedores tbody tr')[indice].querySelector('.gatilho') as HTMLButtonElement).click();
      fixture.detectChanges();
      const botoes = Array.from(el.querySelectorAll('.tabela-provedores tbody tr')[indice].querySelectorAll('button'));
      (botoes.find((b) => b.textContent?.trim() === 'Ativar (embedding)') as HTMLButtonElement).click();
      fixture.detectChanges();
    },
    clicarDesativarEmbedding: (indice: number) => {
      (el.querySelectorAll('.tabela-provedores tbody tr')[indice].querySelector('.gatilho') as HTMLButtonElement).click();
      fixture.detectChanges();
      const botoes = Array.from(el.querySelectorAll('.tabela-provedores tbody tr')[indice].querySelectorAll('button'));
      (botoes.find((b) => b.textContent?.trim() === 'Desativar (embedding)') as HTMLButtonElement).click();
      fixture.detectChanges();
    },
    clicarTestar: (indice: number) => {
      (el.querySelectorAll('.tabela-provedores tbody tr')[indice].querySelector('.gatilho') as HTMLButtonElement).click();
      fixture.detectChanges();
      const botoes = Array.from(el.querySelectorAll('.tabela-provedores tbody tr')[indice].querySelectorAll('button'));
      (botoes.find((b) => b.textContent?.includes('Testar conexão')) as HTMLButtonElement).click();
      fixture.detectChanges();
    },
    clicarDesativar: (indice: number) => {
      (el.querySelectorAll('.tabela-provedores tbody tr')[indice].querySelector('.gatilho') as HTMLButtonElement).click();
      fixture.detectChanges();
      const botoes = Array.from(el.querySelectorAll('.tabela-provedores tbody tr')[indice].querySelectorAll('button'));
      (botoes.find((b) => b.textContent?.trim() === 'Desativar (chat)') as HTMLButtonElement).click();
      fixture.detectChanges();
    },
    clicarApagar: (indice: number) => {
      (el.querySelectorAll('.tabela-provedores tbody tr')[indice].querySelector('.gatilho') as HTMLButtonElement).click();
      fixture.detectChanges();
      const botoes = Array.from(el.querySelectorAll('.tabela-provedores tbody tr')[indice].querySelectorAll('button'));
      (botoes.find((b) => b.textContent?.includes('Apagar')) as HTMLButtonElement).click();
      fixture.detectChanges();
    },
    confirmarApagar: () => {
      const botoes = Array.from(el.querySelectorAll('app-confirmacao-dialog button')) as HTMLButtonElement[];
      (botoes.find((b) => b.textContent?.includes('Apagar')) as HTMLButtonElement).click();
      fixture.detectChanges();
    },
    botaoSalvarProvedor: () =>
      Array.from(el.querySelectorAll('app-dialog .rodape-form button')).find(
        (b) => b.textContent?.includes('Criar provedor') || b.textContent?.includes('Salvar alterações'),
      ) as HTMLButtonElement,
    abrirConfiguracoesTeto: () => {
      (el.querySelector('button[aria-label="Configurações de tokens"]') as HTMLButtonElement).click();
      fixture.detectChanges();
    },
    campoTeto: () => el.querySelector('.linha-teto input') as HTMLInputElement,
    interruptorTeto: () => el.querySelector('app-interruptor .interruptor') as HTMLButtonElement,
    ativarTeto: () => {
      (el.querySelector('app-interruptor .interruptor') as HTMLButtonElement).click();
      fixture.detectChanges();
    },
    botaoSalvarTeto: () =>
      Array.from(el.querySelectorAll('button')).find((b) => b.textContent?.includes('Salvar teto')) as HTMLButtonElement,
    digitarTeto: (valorTexto: string) => {
      const campo = el.querySelector('.linha-teto input') as HTMLInputElement;
      campo.value = valorTexto;
      campo.dispatchEvent(new Event('input'));
      fixture.detectChanges();
    },
    abrirAba: (rotulo: 'Geral' | 'Por usuário') => {
      const aba = Array.from(el.querySelectorAll('button.aba')).find(
        (b) => b.textContent?.trim() === rotulo,
      ) as HTMLButtonElement;
      aba.click();
      fixture.detectChanges();
    },
    botaoVerTour: () =>
      Array.from(el.querySelectorAll('button')).find((b) => b.textContent?.includes('Veja um exemplo guiado')) as
        | HTMLButtonElement
        | undefined,
    botaoAbrirFecharTabela: () =>
      Array.from(el.querySelectorAll('.cabecalho-secao button')).find(
        (b) => b.getAttribute('aria-label')?.includes('lista de provedores'),
      ) as HTMLButtonElement,
  };
}

describe('ProvedoresLlm', () => {
  afterEach(() => {
    TestBed.inject(HttpTestingController).verify();
  });

  describe('cadastro de provedores', () => {
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
      const { linhasProvedores } = criar();

      expect(linhasProvedores()[0].textContent).toContain('Ativo');
      expect(linhasProvedores()[0].textContent).toContain('Sem chave');
      expect(linhasProvedores()[1].textContent).toContain('Inativo');
      expect(linhasProvedores()[1].textContent).toContain('Configurada');
    });

    it('só o provedor inativo mostra o botão "Ativar" no menu de ações', () => {
      const { linhasProvedores, abrirMenuAcoes } = criar();

      abrirMenuAcoes(0);
      expect(
        Array.from(linhasProvedores()[0].querySelectorAll('button')).some((b) => b.textContent?.includes('Ativar')),
      ).toBe(false);

      abrirMenuAcoes(1);
      expect(
        Array.from(linhasProvedores()[1].querySelectorAll('button')).some((b) => b.textContent?.includes('Ativar')),
      ).toBe(true);
    });

    it('ativar um provedor chama a rota certa e atualiza a lista com a resposta', () => {
      const { fixture, clicarAtivar, http, linhasProvedores } = criar();

      clicarAtivar(1);

      const requisicao = http.expectOne(
        (req) => req.url.endsWith('/api/ti/provedores-llm/2/ativar') && req.method === 'POST',
      );
      requisicao.flush([
        { ...PROVEDOR_OLLAMA, ativo: false },
        { ...PROVEDOR_OCI, ativo: true },
      ]);
      fixture.detectChanges();

      expect(linhasProvedores()[1].textContent).toContain('Ativo');
    });

    it('clicar em Ativar fecha o menu de ações na hora, sem esperar a resposta do servidor', () => {
      const { clicarAtivar, linhasProvedores, http } = criar();

      clicarAtivar(1);

      expect(linhasProvedores()[1].querySelector('.painel')).toBeNull();

      http.expectOne((req) => req.url.endsWith('/api/ti/provedores-llm/2/ativar') && req.method === 'POST').flush([
        { ...PROVEDOR_OLLAMA, ativo: false },
        { ...PROVEDOR_OCI, ativo: true },
      ]);
    });

    it('só o provedor ativo mostra o botão "Desativar (chat)" no menu de ações', () => {
      const { linhasProvedores, abrirMenuAcoes } = criar();

      abrirMenuAcoes(0);
      expect(
        Array.from(linhasProvedores()[0].querySelectorAll('button')).some(
          (b) => b.textContent?.trim() === 'Desativar (chat)',
        ),
      ).toBe(true);

      abrirMenuAcoes(1);
      expect(
        Array.from(linhasProvedores()[1].querySelectorAll('button')).some(
          (b) => b.textContent?.trim() === 'Desativar (chat)',
        ),
      ).toBe(false);
    });

    it('desativar chama a rota certa e volta a lista pro fallback do Ollama, sem apagar nada', () => {
      const { fixture, clicarDesativar, http, linhasProvedores, texto } = criar();

      clicarDesativar(0);

      const requisicao = http.expectOne(
        (req) => req.url.endsWith('/api/ti/provedores-llm/desativar') && req.method === 'POST',
      );
      requisicao.flush([
        { ...PROVEDOR_OLLAMA, ativo: false },
        { ...PROVEDOR_OCI, ativo: false },
      ]);
      fixture.detectChanges();

      expect(linhasProvedores()[0].textContent).toContain('Inativo');
      expect(texto()).toContain('Ollama local');
      expect(texto()).toContain('OCI Generative AI — gpt-oss-120b');
    });

    it('apagar pede confirmação antes de chamar o backend', () => {
      const { clicarApagar, texto, http } = criar();

      clicarApagar(0);

      expect(texto()).toContain('Apagar o provedor "Ollama local"?');
      http.expectNone((req) => req.method === 'DELETE');
    });

    it('apagar o provedor ativo avisa que o sistema volta pro modelo de IA padrão', () => {
      const { clicarApagar, texto } = criar();

      clicarApagar(0); // PROVEDOR_OLLAMA está ativo

      expect(texto()).toContain('sistema volta a usar o modelo de IA padrão configurado');
    });

    it('confirmar apagar chama DELETE e remove da lista', () => {
      const { fixture, clicarApagar, confirmarApagar, http, linhasProvedores } = criar();

      clicarApagar(0);
      confirmarApagar();

      http.expectOne((req) => req.url.endsWith('/api/ti/provedores-llm/1') && req.method === 'DELETE').flush({});
      fixture.detectChanges();

      expect(linhasProvedores().length).toBe(1);
      expect(linhasProvedores()[0].textContent).toContain('OCI Generative AI');
    });

    it('abrir o diálogo de criação começa com os campos vazios', () => {
      const { abrirCriar, texto } = criar();

      abrirCriar();

      expect(texto()).toContain('Novo provedor');
    });

    it('criar sem preencher nome/endereço/modelo mostra erro e não chama o backend', () => {
      const { fixture, abrirCriar, botaoSalvarProvedor, texto, http } = criar();

      abrirCriar();
      botaoSalvarProvedor().click();
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

    it('clicar em Editar fecha o menu de ações da linha, não deixa os dois abertos ao mesmo tempo', () => {
      const { abrirEditar, linhasProvedores } = criar();

      abrirEditar(1);

      expect(linhasProvedores()[1].querySelector('.painel')).toBeNull();
    });
  });

  describe('tabela de provedores colapsável', () => {
    it('começa fechada por padrão', () => {
      TestBed.configureTestingModule({
        imports: [ProvedoresLlm],
        providers: [
          provideRouter([]),
          provideHttpClient(),
          provideHttpClientTesting(),
          { provide: TetoTokensIa, useValue: tetoTokensIaFalso() },
          { provide: UsoIa, useValue: usoIaFalso() },
        ],
      });
      const fixture = TestBed.createComponent(ProvedoresLlm);
      const http = TestBed.inject(HttpTestingController);
      http.expectOne((req) => req.url.endsWith('/api/ti/provedores-llm') && req.method === 'GET').flush([PROVEDOR_OLLAMA]);
      fixture.detectChanges();

      expect(fixture.nativeElement.querySelector('.tabela-provedores')).toBeNull();
    });

    it('clicar no botão de abrir/fechar mostra e esconde a lista', () => {
      const { fixture, botaoAbrirFecharTabela } = criar();

      // `criar()` já abre a tabela pra não quebrar o resto dos testes —
      // fecha primeiro pra testar o toggle de verdade.
      botaoAbrirFecharTabela().click();
      fixture.detectChanges();
      expect(fixture.nativeElement.querySelector('.tabela-provedores')).toBeNull();

      botaoAbrirFecharTabela().click();
      fixture.detectChanges();
      expect(fixture.nativeElement.querySelector('.tabela-provedores')).not.toBeNull();
    });
  });

  describe('idade da credencial', () => {
    it('mostra há quantos dias a credencial foi configurada', () => {
      const dezDiasAtras = new Date(Date.now() - 10 * 24 * 60 * 60 * 1000).toISOString();
      const provedor = { ...PROVEDOR_OCI, credencial_atualizada_em: dezDiasAtras };
      const { texto } = criar([PROVEDOR_OLLAMA, provedor]);

      expect(texto()).toContain('há 10 dias');
    });

    it('credencial com mais de 90 dias mostra aviso pra renovar, não o selo "Configurada"', () => {
      const noventaEUmDiasAtras = new Date(Date.now() - 91 * 24 * 60 * 60 * 1000).toISOString();
      const provedor = { ...PROVEDOR_OCI, credencial_atualizada_em: noventaEUmDiasAtras };
      const { texto, linhasProvedores } = criar([PROVEDOR_OLLAMA, provedor]);

      expect(texto()).toContain('Renovar');
      expect(linhasProvedores()[1].textContent).not.toContain('Configurada');
    });

    it('credencial recente não mostra aviso', () => {
      const { texto } = criar([PROVEDOR_OLLAMA, PROVEDOR_OCI]);

      expect(texto()).not.toContain('Renovar');
    });

    it('provedor sem chave nenhuma não mostra idade de credencial', () => {
      const { linhasProvedores } = criar([PROVEDOR_OLLAMA, PROVEDOR_OCI]);

      expect(linhasProvedores()[0].textContent).not.toContain('há ');
    });
  });

  describe('OCI nativo e capacidades', () => {
    it('escolher "OCI (SDK nativo)" esconde endereço/chave de API e mostra os campos da OCI', () => {
      const { fixture, abrirCriar, texto } = criar();

      abrirCriar();
      fixture.componentInstance.formTipoConexao.set('oci_nativo');
      fixture.detectChanges();

      expect(texto()).not.toContain('Endereço (URL base)');
      expect(texto()).not.toContain('Chave de API');
      expect(texto()).toContain('User OCID');
      expect(texto()).toContain('Chave privada');
    });

    it('abrir o diálogo de criação já vem com "Chat" marcado e "Embedding" desmarcado', () => {
      const { fixture, abrirCriar } = criar();

      abrirCriar();

      expect(fixture.componentInstance.formCapacidadeChat()).toBe(true);
      expect(fixture.componentInstance.formCapacidadeEmbedding()).toBe(false);
    });

    it('desmarcar as duas capacidades impede salvar e mostra o erro', () => {
      const { fixture, abrirCriar, botaoSalvarProvedor, texto, http } = criar();

      abrirCriar();
      fixture.componentInstance.formNome.set('n');
      fixture.componentInstance.formBaseUrl.set('http://x');
      fixture.componentInstance.formModelo.set('m');
      fixture.componentInstance.formCapacidadeChat.set(false);
      fixture.componentInstance.formCapacidadeEmbedding.set(false);
      fixture.detectChanges();

      botaoSalvarProvedor().click();
      fixture.detectChanges();

      expect(texto()).toContain('Marque ao menos uma capacidade');
      http.expectNone((req) => req.method === 'POST');
    });

    it('criar provedor oci_nativo manda credenciais_extra preenchidas e capacidades certas', () => {
      const { fixture, abrirCriar, botaoSalvarProvedor, http } = criar();

      abrirCriar();
      const c = fixture.componentInstance;
      c.formNome.set('Cohere embed');
      c.formModelo.set('cohere.embed-v4.0');
      c.formTipoConexao.set('oci_nativo');
      c.formCapacidadeChat.set(false);
      c.formCapacidadeEmbedding.set(true);
      c.formUserOcid.set('ocid1.user.oc1..u');
      c.formFingerprint.set('aa:bb');
      c.formTenancyOcid.set('ocid1.tenancy.oc1..t');
      c.formRegiao.set('sa-saopaulo-1');
      c.formCompartmentId.set('ocid1.compartment.oc1..c');
      c.formChavePrivada.set('chave-privada-de-teste');
      fixture.detectChanges();

      botaoSalvarProvedor().click();
      fixture.detectChanges();

      const requisicao = http.expectOne((req) => req.url.endsWith('/api/ti/provedores-llm') && req.method === 'POST');
      expect(requisicao.request.body.capacidades).toEqual(['embedding']);
      expect(requisicao.request.body.credenciais_extra).toEqual({
        user_ocid: 'ocid1.user.oc1..u',
        fingerprint: 'aa:bb',
        tenancy_ocid: 'ocid1.tenancy.oc1..t',
        regiao: 'sa-saopaulo-1',
        compartment_id: 'ocid1.compartment.oc1..c',
        chave_privada: 'chave-privada-de-teste',
      });
      requisicao.flush(PROVEDOR_OCI);
      // `salvar()` bem-sucedido recarrega a lista — libera esse GET a mais
      // pra não sobrar requisição presa pro `afterEach` reclamar.
      http.expectOne((req) => req.url.endsWith('/api/ti/provedores-llm') && req.method === 'GET').flush([]);
    });

    it('editar oci_nativo sem preencher os campos de credencial não manda credenciais_extra', () => {
      const provedorOci = { ...PROVEDOR_OCI, tipo_conexao: 'oci_nativo', capacidades: ['embedding'] };
      const { fixture, abrirEditar, botaoSalvarProvedor, http } = criar([PROVEDOR_OLLAMA, provedorOci]);

      abrirEditar(1);
      botaoSalvarProvedor().click();
      fixture.detectChanges();

      const requisicao = http.expectOne(
        (req) => req.url.endsWith(`/api/ti/provedores-llm/${provedorOci.id}`) && req.method === 'PATCH',
      );
      expect(requisicao.request.body.credenciais_extra).toBeUndefined();
      requisicao.flush(provedorOci);
      http.expectOne((req) => req.url.endsWith('/api/ti/provedores-llm') && req.method === 'GET').flush([]);
    });

    it('provedor sem capacidade de chat e inativo não mostra o botão "Ativar (chat)", só "Ativar (embedding)"', () => {
      const provedorEmbedding = { ...PROVEDOR_OCI, ativo: false, capacidades: ['embedding'] };
      const { linhasProvedores, abrirMenuAcoes } = criar([PROVEDOR_OLLAMA, provedorEmbedding]);

      abrirMenuAcoes(1);

      const textosBotoes = Array.from(linhasProvedores()[1].querySelectorAll('button')).map((b) =>
        b.textContent?.trim(),
      );
      expect(textosBotoes).not.toContain('Ativar (chat)');
      expect(textosBotoes).toContain('Ativar (embedding)');
    });

    it('ativar um provedor pra embedding chama a rota certa e atualiza a lista', () => {
      const provedorEmbedding = { ...PROVEDOR_OCI, id: 3, ativo: false, ativo_embedding: false, capacidades: ['embedding'] };
      const { fixture, clicarAtivarEmbedding, http, linhasProvedores } = criar([PROVEDOR_OLLAMA, provedorEmbedding]);

      clicarAtivarEmbedding(1);

      const requisicao = http.expectOne(
        (req) => req.url.endsWith('/api/ti/provedores-llm/3/ativar-embedding') && req.method === 'POST',
      );
      requisicao.flush([PROVEDOR_OLLAMA, { ...provedorEmbedding, ativo_embedding: true }]);
      fixture.detectChanges();

      expect(linhasProvedores()[1].textContent).toContain('Ativo (embedding)');
    });

    it('desativar o embedding chama a rota certa, sem mexer no ativo de chat', () => {
      const provedorEmbedding = { ...PROVEDOR_OCI, id: 3, ativo: false, ativo_embedding: true, capacidades: ['embedding'] };
      const { fixture, clicarDesativarEmbedding, http, linhasProvedores } = criar([PROVEDOR_OLLAMA, provedorEmbedding]);

      clicarDesativarEmbedding(1);

      const requisicao = http.expectOne(
        (req) => req.url.endsWith('/api/ti/provedores-llm/desativar-embedding') && req.method === 'POST',
      );
      requisicao.flush([PROVEDOR_OLLAMA, { ...provedorEmbedding, ativo_embedding: false }]);
      fixture.detectChanges();

      expect(linhasProvedores()[1].textContent).toContain('Inativo');
      expect(linhasProvedores()[0].textContent).toContain('Ativo (chat)'); // chat de outro provedor intacto
    });

    it('mostra um selo por capacidade na linha da tabela', () => {
      const provedorDuasCapacidades = { ...PROVEDOR_OCI, capacidades: ['chat', 'embedding'] };
      const { linhasProvedores } = criar([PROVEDOR_OLLAMA, provedorDuasCapacidades]);

      const texto = linhasProvedores()[1].textContent ?? '';
      expect(texto).toContain('Chat');
      expect(texto).toContain('Embedding');
    });
  });

  describe('testar conexão', () => {
    it('clicar em "Testar conexão" chama a rota certa', () => {
      const { clicarTestar, http } = criar();

      clicarTestar(0);

      const requisicao = http.expectOne(
        (req) => req.url.endsWith('/api/ti/provedores-llm/1/testar') && req.method === 'POST',
      );
      requisicao.flush({ ok: true });
    });
  });

  describe('tour guiado', () => {
    it('o botão "Veja um exemplo guiado" só aparece ao criar, não ao editar', () => {
      const { abrirCriar, abrirEditar, botaoVerTour } = criar();

      abrirCriar();
      expect(botaoVerTour()).toBeDefined();

      abrirEditar(1);
      expect(botaoVerTour()).toBeUndefined();
    });

    it('clicar no botão abre o tour', () => {
      const { fixture, abrirCriar, botaoVerTour } = criar();
      abrirCriar();

      botaoVerTour()?.click();
      fixture.detectChanges();

      expect(fixture.componentInstance.tourAberto()).toBe(true);
    });

    it('fechar o tour (Pular/Esc/Concluir) não altera nenhum campo do formulário — é só apontar e explicar', () => {
      const { fixture, abrirCriar, botaoVerTour } = criar();
      abrirCriar();
      botaoVerTour()?.click();
      fixture.detectChanges();

      // Simula o output `(fechar)` do app-tour-guiado, do jeito que o
      // "Pular"/Esc/"Concluir" dele realmente dispara.
      fixture.componentInstance.fecharTour();
      fixture.detectChanges();

      expect(fixture.componentInstance.tourAberto()).toBe(false);
      expect(fixture.componentInstance.formNome()).toBe('');
      expect(fixture.componentInstance.formBaseUrl()).toBe('');
      expect(fixture.componentInstance.formModelo()).toBe('');
    });
  });

  describe('consumo e custo', () => {
    it('carrega o consumo e o teto ao abrir a página', () => {
      const configuracoes = tetoTokensIaFalso();
      const usoIa = usoIaFalso();

      criar([], configuracoes, usoIa);

      expect(configuracoes.carregar).toHaveBeenCalled();
      expect(usoIa.carregar).toHaveBeenCalled();
    });

    it('consumo de IA atualiza sozinho, sem precisar de F5', () => {
      vi.useFakeTimers();
      const usoIa = usoIaFalso();

      criar([], tetoTokensIaFalso(), usoIa);

      expect(usoIa.carregar).toHaveBeenCalledTimes(1); // carga inicial, ao entrar na tela

      vi.advanceTimersByTime(30_000);
      expect(usoIa.carregar).toHaveBeenCalledTimes(2);

      vi.advanceTimersByTime(30_000);
      expect(usoIa.carregar).toHaveBeenCalledTimes(3);

      vi.useRealTimers();
    });

    it('o diálogo de configurações de teto começa fechado', () => {
      const { texto } = criar([]);

      expect(texto()).not.toContain('Salvar teto');
    });

    it('clicar na engrenagem abre o diálogo com o teto já preenchido', () => {
      const { abrirConfiguracoesTeto, campoTeto, texto } = criar([]);

      abrirConfiguracoesTeto();

      expect(texto()).toContain('Configurações de tokens');
      expect(campoTeto().value).toBe('1000');
    });

    it('sem consumo registrado, mostra a mensagem de lista vazia na aba Geral', () => {
      const { texto } = criar([]);

      expect(texto()).toContain('Nenhum consumo ainda');
    });

    it('mostra a tabela de consumo por provedor/modelo', () => {
      const usoIa = usoIaFalso({
        consumo: [
          {
            provedor: 'OCI Generative AI — gpt-oss-120b',
            modelo: 'openai.gpt-oss-120b',
            chamadas: 5,
            tokens_entrada: 134,
            tokens_saida: 96,
            tokens_raciocinio: 62,
            tokens_total: 230,
            custo_estimado: null,
            moeda: null,
            custo_brl: null,
          },
        ],
      });
      const { linhasConsumo } = criar([], tetoTokensIaFalso(), usoIa);

      const texto = linhasConsumo()[0].textContent ?? '';
      expect(texto).toContain('134');
      expect(texto).toContain('96');
      expect(texto).toContain('62');
    });

    it('linha sem provedor cadastrado hoje mostra "—" no custo estimado', () => {
      const usoIa = usoIaFalso({
        consumo: [
          {
            provedor: 'Modelo de IA (padrão)',
            modelo: 'qwen2.5-coder:7b',
            chamadas: 5,
            tokens_entrada: 134,
            tokens_saida: 96,
            tokens_raciocinio: 0,
            tokens_total: 230,
            custo_estimado: null,
            moeda: null,
            custo_brl: null,
          },
        ],
      });
      const { linhasConsumo } = criar([], tetoTokensIaFalso(), usoIa);

      expect(linhasConsumo()[0].textContent).toContain('—');
    });

    it('linha que bate com um provedor cadastrado mostra o custo estimado', () => {
      const usoIa = usoIaFalso({
        consumo: [
          {
            provedor: 'OCI Generative AI — gpt-oss-120b',
            modelo: 'openai.gpt-oss-120b',
            chamadas: 5,
            tokens_entrada: 1000,
            tokens_saida: 1000,
            tokens_raciocinio: 0,
            tokens_total: 2000,
            custo_estimado: 0.03,
            moeda: 'R$',
            custo_brl: null,
          },
        ],
      });
      const { texto } = criar([], tetoTokensIaFalso(), usoIa);

      expect(texto()).toContain('R$ 0,03');
    });

    it('linha em dólar com cotação disponível mostra a conversão em R$', () => {
      const usoIa = usoIaFalso({
        consumo: [
          {
            provedor: 'OCI Generative AI — Llama 3.3',
            modelo: 'meta.llama-3_3-70b-instruct',
            chamadas: 5,
            tokens_entrada: 1000,
            tokens_saida: 1000,
            tokens_raciocinio: 0,
            tokens_total: 2000,
            custo_estimado: 0.0002,
            moeda: 'US$',
            custo_brl: 0.001,
          },
        ],
      });
      const { texto } = criar([], tetoTokensIaFalso(), usoIa);

      expect(texto()).toContain('US$ 0,0002');
      expect(texto()).toContain('≈ R$ 0,001');
    });

    it('mostra o donut de consumo por provedor quando há dado', () => {
      const usoIa = usoIaFalso({
        consumo: [
          {
            provedor: 'oci_openai',
            modelo: 'openai.gpt-oss-120b',
            chamadas: 5,
            tokens_entrada: 134,
            tokens_saida: 96,
            tokens_raciocinio: 62,
            tokens_total: 230,
            custo_estimado: null,
            moeda: null,
            custo_brl: null,
          },
        ],
      });
      const { fixture } = criar([], tetoTokensIaFalso(), usoIa);

      expect(fixture.nativeElement.querySelector('app-grafico-rosca')).not.toBeNull();
    });

    it('mostra o gráfico de tendência diária quando há dado', () => {
      const usoIa = usoIaFalso({
        porDia: [
          { data: '2026-09-22', chamadas: 3, tokens_entrada: 300, tokens_saida: 150, tokens_total: 450 },
          { data: '2026-09-23', chamadas: 5, tokens_entrada: 500, tokens_saida: 250, tokens_total: 750 },
        ],
      });
      const { fixture } = criar([], tetoTokensIaFalso(), usoIa);

      expect(fixture.nativeElement.querySelector('app-grafico-serie')).not.toBeNull();
    });

    it('modelo vazio mostra "(padrão do provedor)"', () => {
      const usoIa = usoIaFalso({
        consumo: [
          {
            provedor: 'ollama',
            modelo: '',
            chamadas: 3,
            tokens_entrada: 300,
            tokens_saida: 150,
            tokens_raciocinio: 0,
            tokens_total: 450,
            custo_estimado: null,
            moeda: null,
            custo_brl: null,
          },
        ],
      });
      const { texto } = criar([], tetoTokensIaFalso(), usoIa);

      expect(texto()).toContain('(padrão do provedor)');
    });

    it('mostra o percentual do teto consumido hoje', () => {
      // `tokensHojePorDominio` (soma TI+RH) alimenta só o card informativo
      // geral de consumo — o percentual do teto usa `tetoTokensIa.tokensHoje`,
      // que é só do domínio `ti` (teto agora é por departamento).
      const usoIa = usoIaFalso({ tokensHojePorDominio: { ti: 300, rh: 200 } });
      const tetoTokensIa = tetoTokensIaFalso();
      tetoTokensIa.tokensHoje.set(500);

      const { texto } = criar([], tetoTokensIa, usoIa);

      expect(texto()).toContain('500'); // soma ti + rh, no card geral de consumo
      expect(texto()).toContain('50% do teto');
    });

    it('sem teto configurado, mostra aviso de "sem teto" em vez de percentual', () => {
      const tetoTokensIa = tetoTokensIaFalso();
      tetoTokensIa.teto.set(0);

      const { texto, abrirConfiguracoesTeto } = criar([], tetoTokensIa);
      abrirConfiguracoesTeto();

      expect(texto()).toContain('Sem teto configurado');
    });

    it('com teto desativado (0), o campo do valor começa desabilitado', () => {
      const tetoTokensIa = tetoTokensIaFalso();
      tetoTokensIa.teto.set(0);

      const { campoTeto, abrirConfiguracoesTeto } = criar([], tetoTokensIa);
      abrirConfiguracoesTeto();

      expect(campoTeto().disabled).toBe(true);
    });

    it('com teto já ativo (> 0), o campo do valor começa habilitado', () => {
      const { campoTeto, abrirConfiguracoesTeto } = criar([]); // fake padrão já carrega teto = 1000
      abrirConfiguracoesTeto();

      expect(campoTeto().disabled).toBe(false);
    });

    it('ativar o interruptor habilita o campo pra digitar o teto', () => {
      const tetoTokensIa = tetoTokensIaFalso();
      tetoTokensIa.teto.set(0);

      const { campoTeto, ativarTeto, abrirConfiguracoesTeto } = criar([], tetoTokensIa);
      abrirConfiguracoesTeto();
      expect(campoTeto().disabled).toBe(true);

      ativarTeto();

      expect(campoTeto().disabled).toBe(false);
    });

    it('salvar com o teto desativado sempre manda 0, mesmo com número digitado antes de desativar', () => {
      const tetoTokensIa = tetoTokensIaFalso();
      const { abrirConfiguracoesTeto, digitarTeto, ativarTeto, botaoSalvarTeto, fixture } = criar(
        [],
        tetoTokensIa,
      );
      abrirConfiguracoesTeto();
      digitarTeto('5000'); // teto já vem ativo no fake padrão (1000) — digita um novo valor
      ativarTeto(); // desativa de novo (alterna o interruptor que já estava ligado)

      botaoSalvarTeto().click();
      fixture.detectChanges();

      expect(tetoTokensIa.salvar).toHaveBeenCalledWith('ti', 0);
    });

    it('teto inválido (negativo) desabilita "Salvar teto" e mostra o erro', () => {
      const { abrirConfiguracoesTeto, digitarTeto, botaoSalvarTeto, texto } = criar([]);
      abrirConfiguracoesTeto();

      digitarTeto('-5');

      expect(botaoSalvarTeto().disabled).toBe(true);
      expect(texto()).toContain('número inteiro maior que 0');
    });

    it('salvar teto válido chama o serviço com o domínio "ti" e o valor certo, fecha o diálogo', () => {
      const tetoTokensIa = tetoTokensIaFalso();
      const { abrirConfiguracoesTeto, digitarTeto, botaoSalvarTeto, texto, fixture } = criar([], tetoTokensIa);
      abrirConfiguracoesTeto();

      digitarTeto('5000');
      botaoSalvarTeto().click();
      fixture.detectChanges();

      expect(tetoTokensIa.salvar).toHaveBeenCalledWith('ti', 5000);
      expect(texto()).not.toContain('Salvar teto');
    });

    it('erro do servidor ao salvar teto mostra o motivo e mantém o diálogo aberto', () => {
      const erro = new HttpErrorResponse({ status: 400, error: { erro: 'Valor inválido.' } });
      const tetoTokensIa = tetoTokensIaFalso(vi.fn(() => throwError(() => erro)));
      const { abrirConfiguracoesTeto, digitarTeto, botaoSalvarTeto, texto, fixture } = criar([], tetoTokensIa);
      abrirConfiguracoesTeto();

      digitarTeto('5000');
      botaoSalvarTeto().click();
      fixture.detectChanges();

      expect(texto()).toContain('Valor inválido.');
      expect(texto()).toContain('Salvar teto');
    });

    it('abre na aba "Geral" por padrão, sem mostrar a tabela por usuário', () => {
      const usoIa = usoIaFalso({
        porUsuario: [
          {
            usuario_id: '42',
            nome: 'Daniel Faria',
            chamadas: 5,
            tokens_entrada: 300,
            tokens_saida: 150,
            tokens_raciocinio: 0,
            tokens_total: 450,
          },
        ],
      });

      const { texto } = criar([], tetoTokensIaFalso(), usoIa);

      expect(texto()).not.toContain('Daniel Faria');
    });

    it('trocar pra aba "Por usuário" mostra a tabela por usuário, já ordenada como veio do backend', () => {
      const usoIa = usoIaFalso({
        porUsuario: [
          {
            usuario_id: '42',
            nome: 'Daniel Faria',
            chamadas: 20,
            tokens_entrada: 3000,
            tokens_saida: 1500,
            tokens_raciocinio: 0,
            tokens_total: 4500,
          },
          {
            usuario_id: 'sistema',
            nome: 'Sistema/Automático',
            chamadas: 5,
            tokens_entrada: 300,
            tokens_saida: 150,
            tokens_raciocinio: 0,
            tokens_total: 450,
          },
        ],
      });

      const { texto, abrirAba, linhasConsumo } = criar([], tetoTokensIaFalso(), usoIa);
      abrirAba('Por usuário');

      const linhas = linhasConsumo();
      expect(texto()).toContain('Daniel Faria');
      expect(texto()).toContain('Sistema/Automático');
      expect(linhas[0].textContent).toContain('Daniel Faria');
      expect(linhas[1].textContent).toContain('Sistema/Automático');
    });

    it('sem consumo por usuário, mostra a mensagem de lista vazia na aba', () => {
      const { texto, abrirAba } = criar([]);
      abrirAba('Por usuário');

      expect(texto()).toContain('Nenhum consumo ainda');
    });
  });

  describe('modo leitura pro time de TI (2026-09-28)', () => {
    it('quem não é desenvolvedor vê a lista de provedores, mas sem nenhum botão de escrita', () => {
      const { texto, el } = criar(
        [PROVEDOR_OLLAMA, PROVEDOR_OCI],
        tetoTokensIaFalso(),
        usoIaFalso(),
        sessaoFalso(false),
      );

      // Continua vendo os dados — só não pode mexer.
      expect(texto()).toContain('Ollama local');
      expect(texto()).toContain('OCI Generative AI — gpt-oss-120b');

      expect(Array.from(el.querySelectorAll('button')).some((b) => b.textContent?.includes('Novo provedor'))).toBe(
        false,
      );
      expect(el.querySelector('button[aria-label="Configurações de tokens"]')).toBeNull();
      expect(el.querySelectorAll('.tabela-provedores tbody .gatilho').length).toBe(0);
    });

    it('desenvolvedor continua vendo os botões de escrita normalmente', () => {
      const { el } = criar([PROVEDOR_OLLAMA], tetoTokensIaFalso(), usoIaFalso(), sessaoFalso(true));

      expect(Array.from(el.querySelectorAll('button')).some((b) => b.textContent?.includes('Novo provedor'))).toBe(
        true,
      );
      expect(el.querySelector('button[aria-label="Configurações de tokens"]')).not.toBeNull();
      expect(el.querySelectorAll('.tabela-provedores tbody .gatilho').length).toBeGreaterThan(0);
    });

    it('ti_admin (não desenvolvedor) vê a engrenagem de teto, mas não o CRUD de provedores', () => {
      const { el } = criar([PROVEDOR_OLLAMA], tetoTokensIaFalso(), usoIaFalso(), sessaoFalso(false, true));

      expect(el.querySelector('button[aria-label="Configurações de tokens"]')).not.toBeNull();
      expect(Array.from(el.querySelectorAll('button')).some((b) => b.textContent?.includes('Novo provedor'))).toBe(
        false,
      );
      expect(el.querySelectorAll('.tabela-provedores tbody .gatilho').length).toBe(0);
    });
  });
});
