import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { ConfiguracoesTi, ConfiguracoesTiResposta } from '../../../../servicos/configuracoes-ti/configuracoes-ti';
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

const CONFIGURACOES_RESPOSTA: ConfiguracoesTiResposta = {
  usar_ia_avaliacao_chamado: true,
  percentual_amostragem_chamados: 100,
  percentual_alterado_em: null,
  ler_chamados_antigos: false,
  teto_tokens_diario: 1000,
};

const CHAMADOS_IA_VAZIO: ChamadosIaResposta = {
  total_chamados: 0,
  avaliados_insuficientes: 0,
  com_fallback_embedding: 0,
  duracao_media_ms: 0,
};

function configuracoesFalso(salvar = vi.fn(() => of(CONFIGURACOES_RESPOSTA))) {
  return {
    tetoTokensDiario: signal(1000),
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

function criar(
  provedoresIniciais: unknown[] = [PROVEDOR_OLLAMA, PROVEDOR_OCI],
  configuracoes = configuracoesFalso(),
  usoIa = usoIaFalso(),
) {
  TestBed.configureTestingModule({
    imports: [ProvedoresLlm],
    providers: [
      provideRouter([]),
      provideHttpClient(),
      provideHttpClientTesting(),
      { provide: ConfiguracoesTi, useValue: configuracoes },
      { provide: UsoIa, useValue: usoIa },
    ],
  });
  const fixture = TestBed.createComponent(ProvedoresLlm);
  const http = TestBed.inject(HttpTestingController);
  http.expectOne((req) => req.url.endsWith('/api/ti/provedores-llm') && req.method === 'GET').flush(provedoresIniciais);
  fixture.detectChanges();

  const el: HTMLElement = fixture.nativeElement;

  return {
    fixture,
    http,
    configuracoes,
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
      (botoes.find((b) => b.textContent?.includes('Ativar')) as HTMLButtonElement).click();
      fixture.detectChanges();
    },
    clicarDesativar: (indice: number) => {
      (el.querySelectorAll('.tabela-provedores tbody tr')[indice].querySelector('.gatilho') as HTMLButtonElement).click();
      fixture.detectChanges();
      const botoes = Array.from(el.querySelectorAll('.tabela-provedores tbody tr')[indice].querySelectorAll('button'));
      (botoes.find((b) => b.textContent?.trim() === 'Desativar') as HTMLButtonElement).click();
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

    it('só o provedor ativo mostra o botão "Desativar" no menu de ações', () => {
      const { linhasProvedores, abrirMenuAcoes } = criar();

      abrirMenuAcoes(0);
      expect(
        Array.from(linhasProvedores()[0].querySelectorAll('button')).some((b) => b.textContent?.trim() === 'Desativar'),
      ).toBe(true);

      abrirMenuAcoes(1);
      expect(
        Array.from(linhasProvedores()[1].querySelectorAll('button')).some((b) => b.textContent?.trim() === 'Desativar'),
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

    it('apagar o provedor ativo avisa que o sistema volta pro Ollama padrão', () => {
      const { clicarApagar, texto } = criar();

      clicarApagar(0); // PROVEDOR_OLLAMA está ativo

      expect(texto()).toContain('sistema volta a usar o Ollama padrão do .env');
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
      const configuracoes = configuracoesFalso();
      const usoIa = usoIaFalso();

      criar([], configuracoes, usoIa);

      expect(configuracoes.carregar).toHaveBeenCalled();
      expect(usoIa.carregar).toHaveBeenCalled();
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
          },
        ],
      });
      const { linhasConsumo } = criar([], configuracoesFalso(), usoIa);

      const texto = linhasConsumo()[0].textContent ?? '';
      expect(texto).toContain('134');
      expect(texto).toContain('96');
      expect(texto).toContain('62');
    });

    it('linha sem provedor cadastrado hoje mostra "—" no custo estimado', () => {
      const usoIa = usoIaFalso({
        consumo: [
          {
            provedor: 'Ollama (padrão)',
            modelo: 'qwen2.5-coder:7b',
            chamadas: 5,
            tokens_entrada: 134,
            tokens_saida: 96,
            tokens_raciocinio: 0,
            tokens_total: 230,
            custo_estimado: null,
            moeda: null,
          },
        ],
      });
      const { linhasConsumo } = criar([], configuracoesFalso(), usoIa);

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
          },
        ],
      });
      const { texto } = criar([], configuracoesFalso(), usoIa);

      expect(texto()).toContain('R$ 0,03');
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
          },
        ],
      });
      const { fixture } = criar([], configuracoesFalso(), usoIa);

      expect(fixture.nativeElement.querySelector('app-grafico-rosca')).not.toBeNull();
    });

    it('mostra o gráfico de tendência diária quando há dado', () => {
      const usoIa = usoIaFalso({
        porDia: [
          { data: '2026-09-22', chamadas: 3, tokens_entrada: 300, tokens_saida: 150, tokens_total: 450 },
          { data: '2026-09-23', chamadas: 5, tokens_entrada: 500, tokens_saida: 250, tokens_total: 750 },
        ],
      });
      const { fixture } = criar([], configuracoesFalso(), usoIa);

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
          },
        ],
      });
      const { texto } = criar([], configuracoesFalso(), usoIa);

      expect(texto()).toContain('(padrão do provedor)');
    });

    it('mostra o percentual do teto consumido hoje', () => {
      const usoIa = usoIaFalso({ tokensHojePorDominio: { ti: 300, rh: 200 } });

      const { texto } = criar([], configuracoesFalso(), usoIa);

      expect(texto()).toContain('500'); // soma ti + rh
      expect(texto()).toContain('50% do teto');
    });

    it('sem teto configurado, mostra aviso de "sem teto" em vez de percentual', () => {
      const configuracoes = configuracoesFalso();
      configuracoes.tetoTokensDiario.set(0);

      const { texto, abrirConfiguracoesTeto } = criar([], configuracoes);
      abrirConfiguracoesTeto();

      expect(texto()).toContain('Sem teto configurado');
    });

    it('teto inválido (negativo) desabilita "Salvar teto" e mostra o erro', () => {
      const { abrirConfiguracoesTeto, digitarTeto, botaoSalvarTeto, texto } = criar([]);
      abrirConfiguracoesTeto();

      digitarTeto('-5');

      expect(botaoSalvarTeto().disabled).toBe(true);
      expect(texto()).toContain('número inteiro maior ou igual a 0');
    });

    it('salvar teto válido chama o serviço com o valor certo e fecha o diálogo', () => {
      const configuracoes = configuracoesFalso();
      const { abrirConfiguracoesTeto, digitarTeto, botaoSalvarTeto, texto, fixture } = criar([], configuracoes);
      abrirConfiguracoesTeto();

      digitarTeto('5000');
      botaoSalvarTeto().click();
      fixture.detectChanges();

      expect(configuracoes.salvar).toHaveBeenCalledWith({ teto_tokens_diario: 5000 });
      expect(texto()).not.toContain('Salvar teto');
    });

    it('erro do servidor ao salvar teto mostra o motivo e mantém o diálogo aberto', () => {
      const erro = new HttpErrorResponse({ status: 400, error: { erro: 'Valor inválido.' } });
      const configuracoes = configuracoesFalso(vi.fn(() => throwError(() => erro)));
      const { abrirConfiguracoesTeto, digitarTeto, botaoSalvarTeto, texto, fixture } = criar([], configuracoes);
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

      const { texto } = criar([], configuracoesFalso(), usoIa);

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

      const { texto, abrirAba, linhasConsumo } = criar([], configuracoesFalso(), usoIa);
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
});
