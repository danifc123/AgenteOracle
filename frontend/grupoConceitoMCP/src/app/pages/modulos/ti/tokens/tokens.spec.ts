import { HttpErrorResponse } from '@angular/common/http';
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
import { Tokens } from './tokens';

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

function criar(configuracoes = configuracoesFalso(), usoIa = usoIaFalso()) {
  TestBed.configureTestingModule({
    imports: [Tokens],
    providers: [
      provideRouter([]),
      { provide: ConfiguracoesTi, useValue: configuracoes },
      { provide: UsoIa, useValue: usoIa },
    ],
  });
  const fixture = TestBed.createComponent(Tokens);
  fixture.detectChanges();

  const el: HTMLElement = fixture.nativeElement;

  return {
    fixture,
    configuracoes,
    usoIa,
    texto: () => el.textContent ?? '',
    abrirConfiguracoes: () => {
      (el.querySelector('button[aria-label="Configurações de tokens"]') as HTMLButtonElement).click();
      fixture.detectChanges();
    },
    campoTeto: () => el.querySelector('input') as HTMLInputElement,
    botaoSalvar: () =>
      Array.from(el.querySelectorAll('button')).find((b) => b.textContent?.includes('Salvar teto')) as HTMLButtonElement,
    digitarTeto: (valorTexto: string) => {
      const campo = el.querySelector('input') as HTMLInputElement;
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
  };
}

describe('Tokens', () => {
  it('carrega o consumo e o teto ao abrir a página', () => {
    const configuracoes = configuracoesFalso();
    const usoIa = usoIaFalso();

    criar(configuracoes, usoIa);

    expect(configuracoes.carregar).toHaveBeenCalled();
    expect(usoIa.carregar).toHaveBeenCalled();
  });

  it('o diálogo de configurações começa fechado', () => {
    const { texto } = criar();

    expect(texto()).not.toContain('Salvar teto');
  });

  it('clicar na engrenagem abre o diálogo com o teto já preenchido', () => {
    const { abrirConfiguracoes, campoTeto, texto } = criar();

    abrirConfiguracoes();

    expect(texto()).toContain('Configurações de tokens');
    expect(campoTeto().value).toBe('1000');
  });

  it('sem consumo registrado, mostra a mensagem de lista vazia', () => {
    const { texto } = criar();

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
    const { texto } = criar(configuracoesFalso(), usoIa);

    expect(texto()).toContain('OCI Generative AI — gpt-oss-120b');
    expect(texto()).toContain('134');
    expect(texto()).toContain('96');
    expect(texto()).toContain('62');
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
    const { fixture } = criar(configuracoesFalso(), usoIa);

    const linha = fixture.nativeElement.querySelector('.tabela-consumo tbody tr') as HTMLElement;
    expect(linha.textContent).toContain('—');
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
    const { texto } = criar(configuracoesFalso(), usoIa);

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
    const { fixture } = criar(configuracoesFalso(), usoIa);

    expect(fixture.nativeElement.querySelector('app-grafico-rosca')).not.toBeNull();
  });

  it('mostra o gráfico de tendência diária quando há dado', () => {
    const usoIa = usoIaFalso({
      porDia: [
        { data: '2026-09-22', chamadas: 3, tokens_entrada: 300, tokens_saida: 150, tokens_total: 450 },
        { data: '2026-09-23', chamadas: 5, tokens_entrada: 500, tokens_saida: 250, tokens_total: 750 },
      ],
    });
    const { fixture } = criar(configuracoesFalso(), usoIa);

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
    const { texto } = criar(configuracoesFalso(), usoIa);

    expect(texto()).toContain('(padrão do provedor)');
  });

  it('mostra o percentual do teto consumido hoje', () => {
    const usoIa = usoIaFalso({ tokensHojePorDominio: { ti: 300, rh: 200 } });

    const { texto } = criar(configuracoesFalso(), usoIa);

    expect(texto()).toContain('500'); // soma ti + rh
    expect(texto()).toContain('50% do teto');
  });

  it('sem teto configurado, mostra aviso de "sem teto" em vez de percentual', () => {
    const configuracoes = configuracoesFalso();
    configuracoes.tetoTokensDiario.set(0);

    const { texto, abrirConfiguracoes } = criar(configuracoes);
    abrirConfiguracoes();

    expect(texto()).toContain('Sem teto configurado');
  });

  it('teto inválido (negativo) desabilita "Salvar teto" e mostra o erro', () => {
    const { abrirConfiguracoes, digitarTeto, botaoSalvar, texto } = criar();
    abrirConfiguracoes();

    digitarTeto('-5');

    expect(botaoSalvar().disabled).toBe(true);
    expect(texto()).toContain('número inteiro maior ou igual a 0');
  });

  it('salvar teto válido chama o serviço com o valor certo e fecha o diálogo', () => {
    const configuracoes = configuracoesFalso();
    const { abrirConfiguracoes, digitarTeto, botaoSalvar, texto, fixture } = criar(configuracoes);
    abrirConfiguracoes();

    digitarTeto('5000');
    botaoSalvar().click();
    fixture.detectChanges();

    expect(configuracoes.salvar).toHaveBeenCalledWith({ teto_tokens_diario: 5000 });
    expect(texto()).not.toContain('Salvar teto');
  });

  it('erro do servidor ao salvar mostra o motivo e mantém o diálogo aberto', () => {
    const erro = new HttpErrorResponse({ status: 400, error: { erro: 'Valor inválido.' } });
    const configuracoes = configuracoesFalso(vi.fn(() => throwError(() => erro)));
    const { abrirConfiguracoes, digitarTeto, botaoSalvar, texto, fixture } = criar(configuracoes);
    abrirConfiguracoes();

    digitarTeto('5000');
    botaoSalvar().click();
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

    const { texto } = criar(configuracoesFalso(), usoIa);

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

    const { texto, abrirAba, fixture } = criar(configuracoesFalso(), usoIa);
    abrirAba('Por usuário');

    const linhas = Array.from(fixture.nativeElement.querySelectorAll('tbody tr')) as HTMLElement[];
    expect(texto()).toContain('Daniel Faria');
    expect(texto()).toContain('Sistema/Automático');
    expect(linhas[0].textContent).toContain('Daniel Faria');
    expect(linhas[1].textContent).toContain('Sistema/Automático');
  });

  it('sem consumo por usuário, mostra a mensagem de lista vazia na aba', () => {
    const { texto, abrirAba } = criar();
    abrirAba('Por usuário');

    expect(texto()).toContain('Nenhum consumo ainda');
  });
});
