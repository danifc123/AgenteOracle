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
};

function servicoFalso(salvar = vi.fn(() => of(RESPOSTA))) {
  return {
    usarIaAvaliacaoChamado: signal(true),
    percentualAmostragemChamados: signal(20),
    percentualAlteradoEm: signal<string | null>(null),
    lerChamadosAntigos: signal(false),
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

  it('mostra a data de referência quando ela existe', () => {
    const servico = servicoFalso();
    servico.percentualAlteradoEm.set('2026-09-21T14:41:00Z');
    const { texto } = criar(servico);

    expect(texto()).toContain('Chamado antigo é o criado antes da última mudança do percentual (');
  });
});
