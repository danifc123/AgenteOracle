import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { WidgetAtalho } from './widget-atalho';

function criar(props: { rota?: string; href?: string }) {
  TestBed.configureTestingModule({
    imports: [WidgetAtalho],
    providers: [provideRouter([])],
  });
  const fixture = TestBed.createComponent(WidgetAtalho);
  fixture.componentRef.setInput('titulo', 'Central de suporte');
  fixture.componentRef.setInput('texto', 'Texto de apoio');
  fixture.componentRef.setInput('iconeSvg', '<circle cx="12" cy="12" r="9" />');
  if (props.rota) {
    fixture.componentRef.setInput('rota', props.rota);
  }
  if (props.href) {
    fixture.componentRef.setInput('href', props.href);
  }
  fixture.detectChanges();

  return fixture;
}

describe('WidgetAtalho', () => {
  it('renderiza título e texto informados', () => {
    const fixture = criar({ rota: '/ti/seguranca' });

    expect(fixture.nativeElement.textContent).toContain('Central de suporte');
    expect(fixture.nativeElement.textContent).toContain('Texto de apoio');
  });

  it('com rota, usa routerLink de navegação interna', () => {
    const fixture = criar({ rota: '/ti/seguranca' });

    const link: HTMLAnchorElement = fixture.nativeElement.querySelector('a');
    expect(link.getAttribute('href')).toBe('/ti/seguranca');
    expect(link.target).not.toBe('_blank');
  });

  it('sem rota, usa href externo em nova aba', () => {
    const fixture = criar({ href: 'https://suporte.grupoconceito.com/front/central.php' });

    const link: HTMLAnchorElement = fixture.nativeElement.querySelector('a');
    expect(link.getAttribute('href')).toBe('https://suporte.grupoconceito.com/front/central.php');
    expect(link.target).toBe('_blank');
  });
});
