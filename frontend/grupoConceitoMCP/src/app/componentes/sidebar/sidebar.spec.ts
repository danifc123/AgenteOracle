import { provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { Sidebar } from './sidebar';

describe('Sidebar', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Sidebar],
      providers: [provideRouter([])],
    }).compileComponents();
  });

  it('should render the brand logo', async () => {
    const fixture = TestBed.createComponent(Sidebar);
    await fixture.whenStable();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector<HTMLImageElement>('.brand-logo')?.alt).toBe('Grupo Conceito');
  });
});
