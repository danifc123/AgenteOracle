import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { MenuAcoes } from './menu-acoes';

@Component({
  imports: [MenuAcoes],
  template: `
    <app-menu-acoes>
      <button type="button" (click)="cliques = cliques + 1">Item</button>
    </app-menu-acoes>
  `,
})
class HospedeiroTeste {
  cliques = 0;
}

function criar() {
  TestBed.configureTestingModule({ imports: [HospedeiroTeste] });
  const fixture = TestBed.createComponent(HospedeiroTeste);
  fixture.detectChanges();

  const el: HTMLElement = fixture.nativeElement;

  return {
    fixture,
    gatilho: () => el.querySelector('.gatilho') as HTMLButtonElement,
    painel: () => el.querySelector('.painel'),
    itemDoMenu: () => el.querySelector('.painel button') as HTMLButtonElement | null,
  };
}

describe('MenuAcoes', () => {
  it('começa fechado (sem painel no DOM)', () => {
    const { painel } = criar();

    expect(painel()).toBeNull();
  });

  it('clicar no gatilho abre o painel', () => {
    const { fixture, gatilho, painel } = criar();

    gatilho().click();
    fixture.detectChanges();

    expect(painel()).not.toBeNull();
  });

  it('clicar no gatilho de novo fecha o painel (toggle)', () => {
    const { fixture, gatilho, painel } = criar();

    gatilho().click();
    fixture.detectChanges();
    gatilho().click();
    fixture.detectChanges();

    expect(painel()).toBeNull();
  });

  it('clicar fora do menu fecha o painel', () => {
    const { fixture, gatilho, painel } = criar();

    gatilho().click();
    fixture.detectChanges();
    document.body.click();
    fixture.detectChanges();

    expect(painel()).toBeNull();
  });

  it('Esc fecha o painel', () => {
    const { fixture, gatilho, painel } = criar();

    gatilho().click();
    fixture.detectChanges();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    fixture.detectChanges();

    expect(painel()).toBeNull();
  });

  it('clicar num item projetado executa a ação do item e fecha o menu sozinho', () => {
    const { fixture, gatilho, painel, itemDoMenu } = criar();

    gatilho().click();
    fixture.detectChanges();
    itemDoMenu()?.click();
    fixture.detectChanges();

    expect(fixture.componentInstance.cliques).toBe(1);
    expect(painel()).toBeNull();
  });
});
