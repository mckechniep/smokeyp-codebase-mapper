package main

import "fmt"

import (
	"github.com/graph/gosvc/auth"
)

func main() { fmt.Println(auth.Token()) }
