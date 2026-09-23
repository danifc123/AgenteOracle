import { HttpErrorResponse } from '@angular/common/http';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';
import {
  ConfiguracoesTi,
  ConfiguracoesTiResposta,
} from '../../servicos/configuracoes-ti/configuracoes-ti';
import { ConfiguracoesChamados } from './configuracoes-chamados';

const RESPOSTA: ConfiguracoesTiResposta = {
  usar_ia_avaliacao_chamado: true,
  percentual_amostragem_chamados: 20,
  percentual_alterado_em: null,
  ler_chamados_antigos: false,
  provedor_ia: 'ollama',
  modelo_ia: '',
  teto_tokens_diario: 0,
};

function servicoFalso(salvar = vi.fn(() => of(RESPOSTA))) {
  return {
    usarIaAvaliacaoChamado: signal(true),
    percentualAmostragemChamados: signal(20),
    percentualAlteradoEm: signal<string | null>(null),
    lerChamadosAntigos: signal(false),
    provedorIa: signal<'ollama' | 'oci_openai'>('ollama'),
    modeloIa: signal(''),
    salvar,
  };
}

function criar(servico = servicoFalso()) {
  TestBed.configureTestingModule({
    imports: [ConfiguracoesChamados],
    providers: [{ provide: ConfiguracoesTi, useValue: servico }],
  });
  const fixture = TestBed.createComponent(ConfiguracoesChamados);
  fixture.componentRef.setInput('aberto', true);
  fixture.detectChanges();

  const el: HTMLElement = fixture.nativeElement;
  const emitidos: number[] = [];
  fixture.componentInstance.fechar.subscribe(() => emitidos.push(1));

  return {
    fixture,
    servico,
    fechou: () => emitidos.length > 0,
    campo: () => el.querySelector('input') as HTMLInputElement,
    interruptores: () =>
      Array.from(el.querySelectorAll('button[role="switch"]')) as HTMLButtonElement[],
    botaoSalvar: () =>
      Array.from(el.querySelectorAll('.botoes-rodape button')).find((b) =>
        b.textContent?.includes('Salvar'),
      ) as HTMLButtonElement,
    botaoCancelar: () =>
      Array.from(el.querySelectorAll('.botoes-rodape button')).find((b) =>
        b.textContent?.includes('Cancelar'),
      ) as HTMLButtonElement,
    digitar: (texto: string) => {
      const campo = el.querySelector('input') as HTMLInputElement;
      campo.value = texto;
      campo.dispatchEvent(new Event('input'));
      fixture.detectChanges();
    },
    // `app-select-busca` não é um <select> nativo: abre o dropdown (índice
    // 0 = Provedor; 1 = Modelo, só existe depois de escolher OCI) e clica
    // na opção pelo texto exibido.
    escolherNoSelect: (indice: number, rotuloOpcao: string) => {
      const gatilhos = Array.from(el.querySelectorAll('button.gatilho')) as HTMLButtonElement[];
      gatilhos[indice].click();
      fixture.detectChanges();
      const opcoes = Array.from(el.querySelectorAll('button.opcao')) as HTMLButtonElement[];
      const opcao = opcoes.find((botao) => botao.textContent?.trim() === rotuloOpcao);
      opcao?.click();
      fixture.detectChanges();
    },
    texto: () => el.textContent ?? '',
  };
}

describe('ConfiguracoesChamados', () => {
  it('abre com os valores salvos e "Salvar" desabilitado (nada mudou)', () => {
    const { campo, interruptores, botaoSalvar } = criar();

    expect(campo().value).toBe('20');
    expect(interruptores()[0].getAttribute('aria-checked')).toBe('true'); // Usar IA
    expect(interruptores()[1].getAttribute('aria-checked')).toBe('false'); // Ler antigos
    expect(botaoSalvar().disabled).toBe(true);
  });

  it('mudar o percentual habilita "Salvar" e explica a consequência', () => {
    const { digitar, botaoSalvar, texto } = criar();

    digitar('30');

    expect(botaoSalvar().disabled).toBe(false);
    expect(texto()).toContain('passa de 20% para 30%');
    expect(texto()).toContain('De cada 10 chamados novos, 3 serão analisados');
  });

  it('percentual inválido mostra o erro e bloqueia "Salvar"', () => {
    const { digitar, botaoSalvar, fixture } = criar();

    digitar('150');

    expect(fixture.nativeElement.querySelector('[role="alert"]').textContent).toContain('0 a 100');
    expect(botaoSalvar().disabled).toBe(true);
  });

  it('em 100% "Ler chamados antigos" fica desabilitado e explica por quê', () => {
    const { digitar, interruptores, texto } = criar();

    digitar('100');

    expect(interruptores()[1].disabled).toBe(true);
    expect(texto()).toContain('Com 100%, todos os chamados são analisados');
  });

  it('salvar envia SÓ as chaves que mudaram', () => {
    const { digitar, interruptores, botaoSalvar, servico } = criar();

    digitar('30');
    interruptores()[1].click(); // liga "Ler chamados antigos"
    botaoSalvar().click();

    expect(servico.salvar).toHaveBeenCalledWith({
      percentual_amostragem_chamados: 30,
      ler_chamados_antigos: true,
    });
  });

  it('vírgula decimal é aceita e enviada como número', () => {
    const { digitar, botaoSalvar, servico } = criar();

    digitar('12,5');
    botaoSalvar().click();

    expect(servico.salvar).toHaveBeenCalledWith({ percentual_amostragem_chamados: 12.5 });
  });

  it('salvar com sucesso fecha o dialog', () => {
    const { digitar, botaoSalvar, fechou } = criar();

    digitar('30');
    botaoSalvar().click();

    expect(fechou()).toBe(true);
  });

  it('erro do servidor mantém o dialog aberto e mostra o motivo', () => {
    const erro = new HttpErrorResponse({
      status: 403,
      error: { erro: 'Acesso restrito a desenvolvedores.' },
    });
    const servico = servicoFalso(vi.fn(() => throwError(() => erro)));
    const { digitar, botaoSalvar, fechou, fixture } = criar(servico);

    digitar('30');
    botaoSalvar().click();
    fixture.detectChanges();

    expect(fechou()).toBe(false);
    expect(fixture.nativeElement.textContent).toContain('Acesso restrito a desenvolvedores.');
    expect(botaoSalvar().disabled).toBe(false); // dá pra tentar de novo
  });

  it('cancelar fecha sem salvar', () => {
    const { digitar, botaoCancelar, fechou, servico } = criar();

    digitar('30');
    botaoCancelar().click();

    expect(fechou()).toBe(true);
    expect(servico.salvar).not.toHaveBeenCalled();
  });

  it('ao reabrir, o rascunho volta ao que está salvo', () => {
    const { digitar, fixture, campo } = criar();
    digitar('30');

    fixture.componentRef.setInput('aberto', false);
    fixture.detectChanges();
    fixture.componentRef.setInput('aberto', true);
    fixture.detectChanges();

    expect(campo().value).toBe('20');
  });

  it('desligar "Usar IA na avaliação" esconde a seção de Provedor de IA', () => {
    const { interruptores, fixture } = criar();

    expect(fixture.nativeElement.querySelector('button.gatilho')).not.toBeNull();

    interruptores()[0].click(); // desliga "Usar IA na avaliação"
    fixture.detectChanges();

    expect(interruptores()[0].getAttribute('aria-checked')).toBe('false');
    expect(fixture.nativeElement.querySelector('button.gatilho')).toBeNull();
  });

  it('mostra a data de referência quando ela existe', () => {
    const servico = servicoFalso();
    servico.percentualAlteradoEm.set('2026-09-21T14:41:00Z');
    const { texto } = criar(servico);

    expect(texto()).toContain('Chamado antigo é o criado antes da última mudança do percentual (');
  });

  it('trocar pra OCI Generative AI mostra o aviso de correção automática desativada', () => {
    const { escolherNoSelect, texto } = criar();

    escolherNoSelect(0, 'OCI Generative AI');

    expect(texto()).toContain('Correção automática de categoria fica desativada nesse provedor');
  });

  it('salvar com o provedor e o modelo trocados envia só provedor_ia e modelo_ia', () => {
    const { escolherNoSelect, botaoSalvar, servico } = criar();

    escolherNoSelect(0, 'OCI Generative AI');
    escolherNoSelect(1, 'GPT-OSS 120B');
    botaoSalvar().click();

    expect(servico.salvar).toHaveBeenCalledWith({
      provedor_ia: 'oci_openai',
      modelo_ia: 'openai.gpt-oss-120b',
    });
  });

  it('voltar pro Ollama depois de escolher OCI esconde o select de modelo fixo', () => {
    const { escolherNoSelect, fixture } = criar();

    escolherNoSelect(0, 'OCI Generative AI');
    escolherNoSelect(0, 'Ollama (local)');

    // Só o select de Provedor deve sobrar — o de Modelo (fixo da OCI) some,
    // volta a ser o campo de texto livre do Ollama.
    expect(fixture.nativeElement.querySelectorAll('button.gatilho').length).toBe(1);
  });
});
