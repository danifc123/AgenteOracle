import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { Sidebar } from '../componentes/sidebar/sidebar';

@Component({
  selector: 'app-layout',
  imports: [RouterOutlet, Sidebar],
  templateUrl: './layout.html',
  styleUrl: './layout.scss'
})
export class Layout {}
