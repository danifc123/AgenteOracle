import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { SecaoConfiguracao } from './secao-configuracao';

@Component({
  imports: [SecaoConfiguracao],
  template: `<app-secao-configuracao titulo="Avaliação por IA"
    ><p class="conteudo">linha</p></app-secao-configuracao
  >`,
})
class HostDeTeste {}

describe('SecaoConfiguracao', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [HostDeTeste] }).compileComponents();
  });

  it('mostra o título da seção', () => {
    const fixture = TestBed.createComponent(HostDeTeste);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('h3').textContent).toContain('Avaliação por IA');
  });

  it('projeta o conteúdo dentro do cartão', () => {
    const fixture = TestBed.createComponent(HostDeTeste);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.cartao .conteudo').textContent).toBe('linha');
  });

  it('a região é nomeada pelo título (leitor de tela)', () => {
    const fixture = TestBed.createComponent(HostDeTeste);
    fixture.detectChanges();

    const secao: HTMLElement = fixture.nativeElement.querySelector('section');
    const titulo: HTMLElement = fixture.nativeElement.querySelector('h3');
    expect(secao.getAttribute('aria-labelledby')).toBe(titulo.id);
  });
});
