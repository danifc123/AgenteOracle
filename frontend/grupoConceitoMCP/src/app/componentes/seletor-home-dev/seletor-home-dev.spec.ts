import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { vi } from 'vitest';
import { HomeSelecionada } from '../../servicos/home-selecionada/home-selecionada';
import { Sessao } from '../../servicos/sessao/sessao';
import { SeletorHomeDev } from './seletor-home-dev';

@Component({
  imports: [SeletorHomeDev],
  template: `<app-seletor-home-dev />`,
})
class HospedeiroTeste {}

function criar(modulos: string[] = ['ti', 'financeiro']) {
  const homeSelecionada = { modulo: signal('financeiro'), selecionar: vi.fn() };
  const router = { navigateByUrl: vi.fn() };

  TestBed.configureTestingModule({
    imports: [HospedeiroTeste],
    providers: [
      { provide: Sessao, useValue: { modulos: () => modulos, ehDesenvolvedor: () => true } },
      { provide: HomeSelecionada, useValue: homeSelecionada },
      { provide: Router, useValue: router },
    ],
  });
  const fixture = TestBed.createComponent(HospedeiroTeste);
  fixture.detectChanges();

  const el: HTMLElement = fixture.nativeElement;
  return {
    fixture,
    homeSelecionada,
    router,
    select: () => el.querySelector('select.seletor-home') as HTMLSelectElement,
  };
}

describe('SeletorHomeDev', () => {
  it('mostra uma opção por módulo liberado', () => {
    const { select } = criar(['ti', 'financeiro', 'rh']);

    const opcoes = Array.from(select().querySelectorAll('option')).map((o) => o.value);
    expect(opcoes).toEqual(['ti', 'financeiro', 'rh']);
  });

  it('trocar a seleção atualiza HomeSelecionada e navega pra "/"', () => {
    const { select, homeSelecionada, router } = criar(['ti', 'financeiro']);

    select().value = 'ti';
    select().dispatchEvent(new Event('change'));

    expect(homeSelecionada.selecionar).toHaveBeenCalledWith('ti');
    expect(router.navigateByUrl).toHaveBeenCalledWith('/');
  });
});
