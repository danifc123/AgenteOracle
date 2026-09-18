import { TestBed } from '@angular/core/testing';
import { Selo } from './selo';

describe('Selo', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [Selo] }).compileComponents();
  });

  it('renderiza o texto informado', () => {
    const fixture = TestBed.createComponent(Selo);
    fixture.componentRef.setInput('texto', 'Ativa');
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent.trim()).toContain('Ativa');
  });

  it('usa a classe selo--neutro por padrão, sem tom informado', () => {
    const fixture = TestBed.createComponent(Selo);
    fixture.componentRef.setInput('texto', 'Rótulo');
    fixture.detectChanges();

    const selo = fixture.nativeElement.querySelector('.selo');
    expect(selo.classList).toContain('selo--neutro');
  });

  it.each([
    ['ok', 'selo--ok'],
    ['atencao', 'selo--atencao'],
    ['erro', 'selo--erro'],
  ] as const)('tom "%s" aplica a classe %s', (tom, classeEsperada) => {
    const fixture = TestBed.createComponent(Selo);
    fixture.componentRef.setInput('texto', 'Rótulo');
    fixture.componentRef.setInput('tom', tom);
    fixture.detectChanges();

    const selo = fixture.nativeElement.querySelector('.selo');
    expect(selo.classList).toContain(classeEsperada);
  });
});
